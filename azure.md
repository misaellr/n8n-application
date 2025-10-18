# N8N AKS Deployment Guide for Azure

## Overview

This guide provides a comprehensive approach to deploying n8n workflow automation platform on Azure Kubernetes Service (AKS) using Terraform and Helm, following the same architecture principles as the AWS EKS deployment.

### Architecture Components

- **Terraform** provisions a dedicated Azure Virtual Network (VNet) with public and private subnets across multiple availability zones, NAT Gateway, an Azure Kubernetes Service (AKS) cluster, and a managed node pool.
- **Azure RBAC and Managed Identities** are configured for the control plane, worker nodes, and Azure Disk CSI driver integration.
- **Sensitive settings** (n8n encryption key, database credentials, basic auth credentials) are stored in Azure Key Vault and injected into Kubernetes Secrets at deployment time.
- **Terraform** installs the upstream `ingress-nginx` chart (Azure Load Balancer with static Public IPs) but **does NOT deploy n8n**. The n8n application is deployed separately via Helm CLI by a setup script after infrastructure is ready.
- **Database backend** can be SQLite (default, file-based) or PostgreSQL (Azure Database for PostgreSQL - Flexible Server).
- **TLS/HTTPS configuration** is handled as a **post-deployment step** after the Load Balancer is provisioned and DNS can be configured, preventing race conditions with Let's Encrypt validation.
- **Basic authentication** can be configured post-deployment to protect access to n8n with auto-generated credentials stored in Azure Key Vault.

## Prerequisites

### Required Tools

1. **Terraform** (>= 1.6)
   ```bash
   # Install on Linux
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install terraform
   ```

2. **Azure CLI** (>= 2.50)
   ```bash
   # Install on Linux
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   ```

3. **Python 3** (>= 3.7)
   ```bash
   # Usually pre-installed on most systems
   python3 --version
   ```

4. **Helm** (>= 3.0)
   ```bash
   curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
   ```

5. **kubectl**
   ```bash
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
   ```

6. **htpasswd** (for basic auth)
   ```bash
   # Debian/Ubuntu
   sudo apt-get install apache2-utils

   # RHEL/CentOS
   sudo yum install httpd-tools
   ```

### Azure Configuration

1. **Login to Azure**
   ```bash
   az login
   ```

2. **Set your subscription** (if you have multiple subscriptions)
   ```bash
   az account list --output table
   az account set --subscription "<subscription-id-or-name>"
   ```

3. **Verify credentials**
   ```bash
   az account show
   ```

4. **Register required resource providers** (one-time setup)
   ```bash
   az provider register --namespace Microsoft.ContainerService
   az provider register --namespace Microsoft.Network
   az provider register --namespace Microsoft.Storage
   az provider register --namespace Microsoft.KeyVault
   az provider register --namespace Microsoft.DBforPostgreSQL
   ```

## Quick Start

### Phase 1: Infrastructure Deployment (~20-25 minutes)

1. **Clone or navigate to the repository**
   ```bash
   cd n8n-application
   ```

2. **Run the setup script** (to be created)
   ```bash
   python3 setup_azure.py
   ```

3. **Follow the interactive prompts**
   - Select Azure subscription and region (e.g., eastus, westus2, westeurope)
   - Configure AKS cluster settings:
     - Cluster name (default: n8n-aks-cluster)
     - Node VM size (Standard_D2s_v3, Standard_D4s_v3, etc.)
     - Node pool sizing (min/desired/max counts)
   - Configure n8n settings:
     - Kubernetes namespace (default: n8n)
     - Storage size for PVC (default: 10Gi)
     - Hostname (FQDN)
     - Timezone (default: America/Bahia)
   - **Database selection**:
     - SQLite (file-based, minimal cost)
     - PostgreSQL (Azure Database for PostgreSQL Flexible Server)
       - If PostgreSQL: prompts for SKU, storage size, and zone redundancy
   - Encryption key (auto-generated or provide your own)

4. **Infrastructure provisioning**
   The script will create:
   - **Resource Group** for all n8n resources
   - **Virtual Network (VNet)** with public and private subnets across 3 availability zones
   - **NAT Gateway** for private subnet internet access
   - **AKS Cluster** (Kubernetes 1.29+) with managed control plane
   - **Node Pool** (e.g., 2x Standard_D2s_v3 instances) in private subnets
   - **Azure Disk CSI driver** for persistent storage
   - **Default StorageClass** (Azure Premium_LRS, encrypted)
   - **NGINX Ingress Controller** with Azure Load Balancer and static Public IPs
   - **Azure Key Vault** for secrets management
   - **User-Assigned Managed Identity** for AKS workload identity
   - **If PostgreSQL selected**: Azure Database for PostgreSQL Flexible Server, firewall rules, credentials in Key Vault

### Phase 2: Application Deployment (~2-3 minutes)

5. **After Terraform completes**, the script:
   - Configures `kubectl` using AKS credentials
   - If PostgreSQL was selected: Creates Kubernetes Secret with database password from Key Vault
   - Deploys n8n via **Helm CLI**:
     ```bash
     helm install n8n ./helm-azure -n <namespace> --create-namespace \
       --set ingress.enabled=true \
       --set ingress.className=nginx \
       --set ingress.host=<your-hostname> \
       --set ingress.tls.enabled=false \
       --set env.N8N_PROTOCOL=http \
       --set persistence.size=<configured-size> \
       --set-string envSecrets.N8N_ENCRYPTION_KEY=<from-keyvault> \
       --set database.type=<sqlite|postgresql> \
       --set database.postgresql.host=<postgres-fqdn>  # if PostgreSQL
     ```
   - Application is initially deployed with **HTTP only** (no TLS)
   - Waits for deployment readiness (`kubectl wait --for=condition=available deployment/n8n`)

### Phase 3: Load Balancer Retrieval (~1-2 minutes)

6. **The script polls for the Load Balancer public IP**:
   ```bash
   kubectl get svc -n ingress-nginx ingress-nginx-controller \
     -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
   ```

7. **Once ready, displays**:
   ```
   Load Balancer IP:  20.1.2.3
   Static Public IPs: 20.1.2.3
   Access n8n at:     http://20.1.2.3
   ```

### Phase 4: TLS Configuration (Optional, ~5 minutes)

8. **The script prompts**: "Would you like to configure TLS/HTTPS now?"

9. **If Yes**, select one of two options:
   - **Bring Your Own Certificate**: Provide PEM certificate and key files
   - **Let's Encrypt**: Automated certificate via HTTP-01 validation

#### Let's Encrypt Flow:

10. **DNS Configuration Required**:
    ```
       IMPORTANT - DNS Configuration Required
    1. Create DNS A record for: your-domain.com
    2. Point to Load Balancer IP: 20.1.2.3

    Have you configured the DNS record? [y/N]
    ```

11. **You must confirm DNS is configured** before proceeding.

12. **The script then**:
    - Installs cert-manager via Helm
    - Creates a ClusterIssuer for Let's Encrypt
    - Upgrades n8n Helm release with TLS enabled and cert-manager annotations

13. **Let's Encrypt validates** ownership via HTTP-01 challenge and issues certificate (~2-5 minutes)

14. **Access n8n** at `https://your-domain.com`

#### BYO Certificate Flow:

10. **The script prompts** for certificate and key PEM files

11. **Creates Kubernetes TLS secret**:
    ```bash
    kubectl create secret tls n8n-tls -n n8n \
      --cert=path/to/cert.pem \
      --key=path/to/key.pem
    ```

12. **Upgrades n8n** Helm release with TLS enabled

13. **Access n8n** at `https://your-domain.com`

### Phase 4b: Basic Authentication Configuration (Optional, ~1 minute)

15. **After TLS configuration** (or if TLS is skipped), the script prompts: "Would you like to enable basic authentication for n8n?"

16. **If Yes**:
    - Auto-generates credentials:
      - Username: `admin`
      - Password: 12 random alphanumeric characters
    - Stores credentials in Azure Key Vault at secret name `n8n-basic-auth`
    - Displays credentials (you **must save them**)
    - Creates Kubernetes Secret with bcrypt-hashed password
    - Upgrades n8n Helm release with basic auth annotations

17. **Access to n8n** now requires HTTP basic authentication before reaching the n8n login page

## Infrastructure Components

### Networking

**Virtual Network (VNet)**
- CIDR: 10.0.0.0/16 (default, configurable)
- **Public Subnets**: 10.0.0.0/24, 10.0.1.0/24, 10.0.2.0/24 (one per AZ)
- **Private Subnets**: 10.0.100.0/24, 10.0.101.0/24, 10.0.102.0/24 (one per AZ)
- **NAT Gateway**: Attached to public subnets for private subnet internet access
- **Public IPs**: Static IP addresses for NAT Gateway and Load Balancer

**Network Security Groups (NSGs)**
- AKS cluster NSG (managed by AKS)
- Custom NSG for PostgreSQL (if enabled) - allows port 5432 from AKS subnets
- Application Gateway NSG (if using Application Gateway instead of nginx-ingress)

### Compute

**Azure Kubernetes Service (AKS)**
- **Kubernetes Version**: 1.29+ (configurable)
- **Control Plane**: Fully managed by Azure
- **Node Pool**:
  - VM Size: Standard_D2s_v3 (default, configurable)
  - OS Disk: 128GB Premium SSD
  - Count: 2 (default), min: 1, max: 5 (configurable)
  - Type: Virtual Machine Scale Sets (VMSS)
  - Availability: Spread across multiple zones

**Managed Identity**
- **System-assigned identity** for AKS cluster
- **User-assigned identity** for workload identity (Key Vault access)
- **Kubelet identity** for pulling container images from ACR

### Storage

**Azure Disk CSI Driver**
- Built-in to AKS (enabled by default)
- Supports dynamic provisioning of persistent volumes
- Encryption at rest enabled

**Default StorageClass**
- Name: `managed-premium` or custom `azure-disk-premium`
- Type: Premium_LRS (SSD-based)
- Reclaim Policy: Delete
- Volume Binding Mode: WaitForFirstConsumer
- Encryption: Enabled

**Persistent Volume Claims (PVCs)**
- n8n data: 10Gi (default, configurable)
- Storage backed by Azure Premium SSD

### Database (Optional)

**Azure Database for PostgreSQL - Flexible Server**
- **Version**: PostgreSQL 15 (or latest stable)
- **SKU**:
  - Burstable: B1ms, B2s (dev/test, ~$15-30/month)
  - General Purpose: D2s_v3, D4s_v3 (production, ~$100-200/month)
- **Storage**: 32GB-16TB, auto-grow enabled
- **High Availability**: Zone-redundant (optional, adds cost)
- **Backup**: Automated daily backups, 7-day retention
- **Encryption**: At-rest and in-transit (SSL/TLS enforced)
- **Network**: Private endpoint in AKS VNet for secure connectivity

**Connection Details**
- Hostname: `<server-name>.postgres.database.azure.com`
- Port: 5432
- Database: `n8n`
- Username: `n8nadmin` (configurable)
- Password: Auto-generated, stored in Key Vault

### Secrets Management

**Azure Key Vault**
- **Name**: `<project>-kv-<random>`
- **SKU**: Standard (Premium for HSM-backed keys)
- **Access Policy**:
  - Terraform service principal: Get, List, Set secrets
  - AKS Workload Identity: Get secrets
- **Secrets Stored**:
  - `n8n-encryption-key`: 64-character hex encryption key
  - `postgres-password`: Database password (if PostgreSQL enabled)
  - `basic-auth-password`: Basic auth password (if enabled)
- **Networking**: Private endpoint for secure access from AKS
- **Soft Delete**: Enabled with 7-day retention

### Ingress

**NGINX Ingress Controller**
- Deployed via Helm chart from official repository
- **Service Type**: LoadBalancer
- **Azure Load Balancer**:
  - Type: Standard SKU
  - Static Public IP: Pre-allocated for consistent DNS mapping
  - Distribution mode: Hash-based (for session affinity if needed)
- **SSL/TLS Termination**: At ingress level
- **Annotations**:
  - `service.beta.kubernetes.io/azure-load-balancer-resource-group`: Resource group for public IP
  - `service.beta.kubernetes.io/azure-dns-label-name`: DNS label (optional)

**Alternative: Azure Application Gateway**
- Azure-native Layer 7 load balancer
- Integrated WAF (Web Application Firewall)
- SSL/TLS offloading at gateway
- Higher cost (~$125/month + data processing)
- Better for enterprise scenarios requiring WAF

## Configuration Reference

### Terraform Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `azure_subscription_id` | string | - | Azure subscription ID |
| `azure_location` | string | eastus | Azure region (eastus, westus2, westeurope, etc.) |
| `resource_group_name` | string | n8n-rg | Resource group name |
| `project_tag` | string | n8n-app | Project tag for resource naming |
| `vnet_cidr` | string | 10.0.0.0/16 | VNet CIDR block |
| `cluster_name` | string | n8n-aks-cluster | AKS cluster name |
| `kubernetes_version` | string | 1.29 | Kubernetes version |
| `node_vm_size` | string | Standard_D2s_v3 | Node VM size |
| `node_count` | number | 2 | Initial node count |
| `node_min_count` | number | 1 | Minimum node count (autoscaler) |
| `node_max_count` | number | 5 | Maximum node count (autoscaler) |
| `enable_auto_scaling` | bool | true | Enable cluster autoscaler |
| `n8n_host` | string | n8n.example.com | N8N ingress hostname (FQDN) |
| `n8n_namespace` | string | n8n | Kubernetes namespace |
| `n8n_protocol` | string | http | Protocol (http or https) |
| `n8n_persistence_size` | string | 10Gi | PVC storage size |
| `timezone` | string | America/Bahia | Application timezone |
| `n8n_encryption_key` | string (sensitive) | (auto-generated) | 64-char hex encryption key |
| `database_type` | string | sqlite | Database backend (sqlite or postgresql) |
| `postgres_sku` | string | B_Standard_B1ms | PostgreSQL SKU (B_Standard_B1ms, GP_Standard_D2s_v3) |
| `postgres_storage_gb` | number | 32 | PostgreSQL storage in GB |
| `postgres_high_availability` | bool | false | Enable zone redundancy |
| `postgres_version` | string | 15 | PostgreSQL version |
| `enable_basic_auth` | bool | false | Enable basic authentication |
| `enable_nginx_ingress` | bool | true | Install NGINX ingress controller |
| `enable_cert_manager` | bool | false | Install cert-manager (for Let's Encrypt) |

### Helm Values (helm-azure/values.yaml)

Similar to AWS deployment, with Azure-specific adjustments:

| Value | Default | Description |
|-------|---------|-------------|
| `image.repository` | n8nio/n8n | n8n Docker image |
| `image.tag` | latest | n8n version tag |
| `replicaCount` | 1 | Number of pod replicas |
| `service.type` | ClusterIP | Kubernetes service type |
| `ingress.enabled` | true | Enable ingress |
| `ingress.className` | nginx | Ingress class |
| `ingress.host` | n8n.example.com | Ingress hostname |
| `ingress.tls.enabled` | false | Enable TLS (set to true after cert setup) |
| `persistence.enabled` | true | Enable persistent storage |
| `persistence.storageClass` | managed-premium | Azure storage class |
| `persistence.size` | 10Gi | PVC size |
| `resources.limits.memory` | 1Gi | Memory limit |
| `resources.limits.cpu` | 1000m | CPU limit |
| `resources.requests.memory` | 512Mi | Memory request |
| `resources.requests.cpu` | 500m | CPU request |
| `autoscaling.enabled` | false | Enable HPA |
| `autoscaling.minReplicas` | 1 | Min replicas |
| `autoscaling.maxReplicas` | 5 | Max replicas |

## Terraform Module Structure

```
terraform-azure/
   main.tf                 # Main infrastructure definition
   variables.tf            # Input variables
   outputs.tf             # Output values
   providers.tf           # Provider configuration
   network.tf             # VNet, subnets, NSGs
   aks.tf                 # AKS cluster and node pool
   keyvault.tf            # Azure Key Vault configuration
   postgres.tf            # PostgreSQL database (conditional)
   ingress.tf             # NGINX ingress controller
   storage.tf             # Storage classes and CSI driver config
   nginx-ingress-values.tpl  # Helm values template
```

## Manual Deployment Steps

If you prefer to deploy manually without a setup script:

### Step 1: Configure Azure Authentication

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "<subscription-id>"

# Create service principal for Terraform (optional, for CI/CD)
az ad sp create-for-rbac --name "terraform-n8n" --role="Contributor" --scopes="/subscriptions/<subscription-id>"
```

### Step 2: Deploy Infrastructure with Terraform

```bash
# Navigate to Terraform directory
cd terraform-azure

# Create terraform.tfvars
cat > terraform.tfvars <<EOF
azure_subscription_id = "<your-subscription-id>"
azure_location = "eastus"
cluster_name = "n8n-aks-cluster"
n8n_host = "n8n.yourdomain.com"
database_type = "sqlite"  # or "postgresql"
EOF

# Initialize Terraform
terraform init

# Validate configuration
terraform validate

# Preview changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan
```

### Step 3: Configure kubectl

```bash
# Get AKS credentials
az aks get-credentials --resource-group n8n-rg --name n8n-aks-cluster

# Verify connection
kubectl get nodes
```

### Step 4: Retrieve Secrets from Key Vault

```bash
# Get Key Vault name
KV_NAME=$(az keyvault list --resource-group n8n-rg --query "[0].name" -o tsv)

# Get encryption key
ENCRYPTION_KEY=$(az keyvault secret show --vault-name $KV_NAME --name n8n-encryption-key --query value -o tsv)

# If using PostgreSQL, get database password
DB_PASSWORD=$(az keyvault secret show --vault-name $KV_NAME --name postgres-password --query value -o tsv)
```

### Step 5: Deploy n8n with Helm

```bash
# Get PostgreSQL hostname (if applicable)
POSTGRES_HOST=$(az postgres flexible-server show --resource-group n8n-rg --name <server-name> --query fullyQualifiedDomainName -o tsv)

# Deploy n8n (SQLite example)
helm install n8n ./helm-azure -n n8n --create-namespace \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.host=n8n.yourdomain.com \
  --set ingress.tls.enabled=false \
  --set env.N8N_PROTOCOL=http \
  --set-string envSecrets.N8N_ENCRYPTION_KEY=$ENCRYPTION_KEY

# Deploy n8n (PostgreSQL example)
helm install n8n ./helm-azure -n n8n --create-namespace \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.host=n8n.yourdomain.com \
  --set ingress.tls.enabled=false \
  --set env.N8N_PROTOCOL=http \
  --set-string envSecrets.N8N_ENCRYPTION_KEY=$ENCRYPTION_KEY \
  --set database.type=postgresql \
  --set database.postgresql.host=$POSTGRES_HOST \
  --set database.postgresql.port=5432 \
  --set database.postgresql.database=n8n \
  --set database.postgresql.user=n8nadmin \
  --set-string database.postgresql.password=$DB_PASSWORD
```

### Step 6: Get Load Balancer IP

```bash
# Wait for Load Balancer provisioning
kubectl get svc -n ingress-nginx ingress-nginx-controller -w

# Get public IP
LB_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

echo "Access n8n at: http://$LB_IP"
```

### Step 7: Configure DNS

Create an A record in your DNS provider:
- **Host**: n8n (or your subdomain)
- **Type**: A
- **Value**: $LB_IP
- **TTL**: 300 (or your preference)

### Step 8: Configure TLS with Let's Encrypt

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml

# Wait for cert-manager to be ready
kubectl wait --for=condition=available --timeout=300s deployment/cert-manager -n cert-manager

# Create ClusterIssuer
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-production
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-production
    solvers:
    - http01:
        ingress:
          class: nginx
EOF

# Upgrade n8n with TLS enabled
helm upgrade n8n ./helm-azure -n n8n \
  --reuse-values \
  --set ingress.tls.enabled=true \
  --set env.N8N_PROTOCOL=https \
  --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt-production'

# Watch certificate issuance
kubectl get certificate -n n8n -w
```

## Post-Deployment Verification

```bash
# Check AKS cluster status
az aks show --resource-group n8n-rg --name n8n-aks-cluster --query provisioningState -o tsv

# Verify nodes
kubectl get nodes -o wide

# Check n8n deployment
kubectl get all -n n8n
kubectl get pvc -n n8n
kubectl get ingress -n n8n

# Check ingress controller
kubectl get all -n ingress-nginx

# View n8n logs
kubectl logs -f deployment/n8n -n n8n

# If using PostgreSQL, verify database connection
kubectl exec -it deployment/n8n -n n8n -- sh
# Inside container: test database connectivity
# nc -zv <postgres-host> 5432
```

## Cost Estimation

### Monthly Cost Breakdown (East US region)

**SQLite Deployment (Minimal)**
- AKS Control Plane: ~$73/month
- Node Pool (2x Standard_D2s_v3): ~$140/month
- NAT Gateway: ~$33/month (includes 1TB data processing)
- Load Balancer (Standard): ~$18/month
- Static Public IP: ~$3.60/month
- Premium SSD (128GB OS + 10GB data): ~$25/month
- Key Vault: ~$0.03/month (minimal operations)
- **Total: ~$293/month**

**PostgreSQL Deployment (Burstable)**
- All above: ~$293/month
- Azure Database for PostgreSQL (B1ms, 32GB): ~$15/month
- **Total: ~$308/month**

**PostgreSQL Deployment (General Purpose)**
- All above: ~$293/month
- Azure Database for PostgreSQL (D2s_v3, 128GB, Zone Redundant): ~$200/month
- **Total: ~$493/month**

### Cost Optimization Strategies

1. **Use Burstable VMs** for non-production (B2s instead of D2s_v3): Save ~$70/month
2. **Reduce node count** to 1 (not recommended for production): Save ~$70/month
3. **Use Spot instances** for node pool (with caution): Save up to 80% on compute
4. **Reserved instances** (1-year or 3-year commitment): Save up to 40% on compute
5. **Azure Hybrid Benefit** (if you have Windows Server licenses): Additional savings
6. **Single NAT Gateway** instead of per-AZ: Already optimized in this design
7. **Scheduled auto-scaling** to 0 nodes during off-hours (dev/test only): Save ~50% on compute
8. **Use Basic Load Balancer** (not recommended for production): Save ~$15/month

## Operational Best Practices

### Monitoring and Logging

**Azure Monitor for Containers**
```bash
# Enable Container Insights on AKS cluster
az aks enable-addons --resource-group n8n-rg --name n8n-aks-cluster --addons monitoring

# View logs in Azure Portal
# Navigate to: AKS cluster -> Insights -> Logs
```

**Log Analytics Queries**
```kusto
// Container logs
ContainerLog
| where ContainerName == "n8n"
| order by TimeGenerated desc
| take 100

// Pod inventory
KubePodInventory
| where Namespace == "n8n"
| distinct Name, ContainerStatus
```

**Application Insights** (optional)
- Integrate n8n with Application Insights for APM
- Track workflow execution times, errors, and dependencies

### Backup and Disaster Recovery

**AKS Configuration Backup**
```bash
# Backup AKS cluster configuration
az aks show --resource-group n8n-rg --name n8n-aks-cluster > aks-backup.json

# Export Kubernetes resources
kubectl get all,pvc,secrets,configmaps -n n8n -o yaml > n8n-k8s-backup.yaml
```

**PostgreSQL Backup** (automated)
- Point-in-time restore (PITR) up to 35 days
- Geo-redundant backups (optional)
- Manual backup:
  ```bash
  az postgres flexible-server backup create --resource-group n8n-rg --name <server-name> --backup-name manual-backup-$(date +%Y%m%d)
  ```

**n8n Data Backup**
- Regular snapshots of Azure Disk PVC
- Export workflows via n8n UI
- Backup encryption key from Key Vault

### High Availability and Scaling

**Multi-Region Deployment** (advanced)
- Deploy identical infrastructure in secondary region
- Use Azure Traffic Manager for DNS-based failover
- Replicate PostgreSQL using read replicas
- Sync workflows and credentials across regions

**Horizontal Pod Autoscaling (HPA)**
```bash
# Enable HPA for n8n deployment
kubectl autoscale deployment n8n -n n8n --min=2 --max=10 --cpu-percent=70

# Or via Helm
helm upgrade n8n ./helm-azure -n n8n \
  --reuse-values \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=2 \
  --set autoscaling.maxReplicas=10 \
  --set autoscaling.targetCPUUtilizationPercentage=70
```

**AKS Cluster Autoscaler**
- Already enabled by default in this deployment
- Automatically scales node pool based on resource requests
- Respects min/max node count settings

### Security Hardening

**Network Policies**
```yaml
# Restrict n8n pod network access
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: n8n-network-policy
  namespace: n8n
spec:
  podSelector:
    matchLabels:
      app: n8n
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 5432  # PostgreSQL
    - protocol: TCP
      port: 443   # HTTPS
    - protocol: TCP
      port: 80    # HTTP
```

**Pod Security Standards**
```bash
# Enable Pod Security Standards for namespace
kubectl label namespace n8n pod-security.kubernetes.io/enforce=restricted
kubectl label namespace n8n pod-security.kubernetes.io/audit=restricted
kubectl label namespace n8n pod-security.kubernetes.io/warn=restricted
```

**Azure Defender for Kubernetes**
```bash
# Enable security recommendations
az security pricing create --name KubernetesService --tier Standard
```

**Key Vault Access Policies**
- Use Azure AD Workload Identity (recommended over Pod Identity)
- Principle of least privilege for secret access
- Audit logs for all secret operations

### Upgrade Procedures

**AKS Kubernetes Version Upgrade**
```bash
# Check available upgrades
az aks get-upgrades --resource-group n8n-rg --name n8n-aks-cluster --output table

# Upgrade cluster (control plane then node pool)
az aks upgrade --resource-group n8n-rg --name n8n-aks-cluster --kubernetes-version 1.30.0
```

**n8n Application Upgrade**
```bash
# Update image tag in Helm values
helm upgrade n8n ./helm-azure -n n8n \
  --reuse-values \
  --set image.tag=1.x.x

# Or update via Helm repository
helm repo update
helm upgrade n8n n8n/n8n -n n8n --reuse-values
```

## Cleanup

### Automated Teardown (Recommended)

Create a teardown script similar to the AWS version:

```bash
python3 teardown_azure.py
```

This will:
1. Uninstall Helm releases (n8n, cert-manager, ingress-nginx)
2. Delete Kubernetes resources (PVCs, secrets)
3. Destroy Terraform infrastructure (AKS, VNet, PostgreSQL, Key Vault)
4. Clean up Azure resource group (optional)

### Manual Cleanup

```bash
# Step 1: Uninstall Helm releases
helm uninstall n8n -n n8n
helm uninstall cert-manager -n cert-manager 2>/dev/null || true
helm uninstall ingress-nginx -n ingress-nginx 2>/dev/null || true

# Step 2: Delete PVCs (to release Azure Disks)
kubectl delete pvc --all -n n8n

# Step 3: Delete namespaces
kubectl delete namespace n8n cert-manager ingress-nginx

# Step 4: Destroy Terraform infrastructure
cd terraform-azure
terraform destroy -auto-approve

# Step 5: (Optional) Delete entire resource group
az group delete --name n8n-rg --yes --no-wait
```

**Important**: Ensure all Helm releases and PVCs are deleted before running `terraform destroy` to avoid orphaned resources.

### Verify Cleanup

```bash
# Check for remaining AKS clusters
az aks list --resource-group n8n-rg --output table

# Check for remaining disks
az disk list --resource-group n8n-rg --output table

# Check for public IPs
az network public-ip list --resource-group n8n-rg --output table

# Check Key Vault (may be in soft-delete state)
az keyvault list-deleted --subscription <subscription-id>

# Purge soft-deleted Key Vault if needed
az keyvault purge --name <keyvault-name>
```

## Troubleshooting

### Common Issues

**AKS Cluster Creation Fails**
- **Error**: "Subscription not registered for Microsoft.ContainerService"
  - **Solution**: `az provider register --namespace Microsoft.ContainerService`
- **Error**: "Insufficient quota for VM family"
  - **Solution**: Request quota increase in Azure Portal or use smaller VM size

**Pods Stuck in Pending**
- **Cause**: Insufficient node resources or PVC provisioning issues
- **Debug**:
  ```bash
  kubectl describe pod <pod-name> -n n8n
  kubectl get events -n n8n --sort-by='.lastTimestamp'
  ```
- **Solution**: Scale node pool or check storage class configuration

**Load Balancer IP Not Assigned**
- **Cause**: Public IP resource not created or NSG blocking traffic
- **Debug**:
  ```bash
  kubectl describe svc ingress-nginx-controller -n ingress-nginx
  az network public-ip list --resource-group <node-resource-group> --output table
  ```
- **Solution**: Verify public IP is created in node resource group (MC_*)

**PostgreSQL Connection Failures**
- **Cause**: Firewall rules or NSG blocking port 5432
- **Debug**:
  ```bash
  # From within n8n pod
  kubectl exec -it deployment/n8n -n n8n -- nc -zv <postgres-host> 5432

  # Check PostgreSQL firewall
  az postgres flexible-server firewall-rule list --resource-group n8n-rg --name <server-name>
  ```
- **Solution**: Add firewall rule for AKS subnet or enable "Allow Azure services"

**Key Vault Access Denied**
- **Cause**: Workload identity not properly configured or access policy missing
- **Debug**:
  ```bash
  # Check pod identity
  kubectl describe pod <pod-name> -n n8n | grep azure.workload.identity

  # Check Key Vault access policies
  az keyvault show --name <keyvault-name> --query properties.accessPolicies
  ```
- **Solution**: Configure workload identity federation or update access policies

**Cert-Manager Certificate Not Issued**
- **Cause**: DNS not resolving, Let's Encrypt validation failing
- **Debug**:
  ```bash
  kubectl describe certificate -n n8n
  kubectl describe certificaterequest -n n8n
  kubectl logs -n cert-manager deployment/cert-manager
  ```
- **Solution**: Verify DNS A record points to Load Balancer IP and is propagated

### Performance Optimization

**n8n Workflow Execution Slow**
1. **Scale up node VM size**: Upgrade to Standard_D4s_v3 or higher
2. **Enable HPA**: Scale to multiple n8n pods for concurrent workflow execution
3. **Optimize PostgreSQL**: Use General Purpose or Memory Optimized SKU
4. **Add Redis**: Cache frequently accessed data (requires additional Redis deployment)
5. **Monitor resource usage**:
   ```bash
   kubectl top nodes
   kubectl top pods -n n8n
   ```

**High Azure Egress Costs**
- Use Azure CDN or Azure Front Door for static content caching
- Implement webhook batching to reduce API calls
- Use VNet service endpoints to avoid internet egress for Azure services

## Azure-Specific Features

### Azure AD Integration

**AKS Azure AD Authentication**
```bash
# Enable Azure AD integration (if not already enabled)
az aks update --resource-group n8n-rg --name n8n-aks-cluster --enable-aad --aad-admin-group-object-ids <group-id>
```

**n8n Azure AD SSO** (requires n8n enterprise license)
- Configure SAML/OAuth2 with Azure AD
- Single sign-on for n8n users
- Centralized user management

### Azure Monitor Workbooks

Create custom dashboards for n8n monitoring:
- Workflow execution metrics
- API request rates
- Database query performance
- Resource utilization trends

### Azure DevOps Integration

**CI/CD Pipeline for n8n Workflows**
```yaml
# azure-pipelines.yml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

steps:
- task: HelmDeploy@0
  inputs:
    connectionType: 'Azure Resource Manager'
    azureSubscription: '<subscription>'
    azureResourceGroup: 'n8n-rg'
    kubernetesCluster: 'n8n-aks-cluster'
    command: 'upgrade'
    chartType: 'FilePath'
    chartPath: './helm-azure'
    releaseName: 'n8n'
    namespace: 'n8n'
    arguments: '--reuse-values --set image.tag=$(Build.BuildId)'
```

## Further Reading

- **n8n Documentation**: https://docs.n8n.io/
- **Azure AKS Best Practices**: https://learn.microsoft.com/en-us/azure/aks/best-practices
- **Azure Kubernetes Service**: https://learn.microsoft.com/en-us/azure/aks/
- **Terraform Azure Provider**: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs
- **Helm Documentation**: https://helm.sh/docs/
- **Azure Database for PostgreSQL**: https://learn.microsoft.com/en-us/azure/postgresql/
- **Azure Key Vault**: https://learn.microsoft.com/en-us/azure/key-vault/
- **cert-manager on AKS**: https://cert-manager.io/docs/installation/kubernetes/

## Summary

This guide provides a comprehensive approach to deploying n8n on Azure Kubernetes Service with:

- **Production-ready infrastructure** using Terraform
- **Secure secrets management** with Azure Key Vault
- **Flexible database options** (SQLite or PostgreSQL)
- **Automated TLS** with Let's Encrypt or BYO certificates
- **Optional basic authentication** for additional security
- **Cost optimization** strategies for different use cases
- **High availability** with multi-zone deployment
- **Monitoring and logging** with Azure Monitor
- **Backup and disaster recovery** procedures

The deployment follows Azure best practices and mirrors the AWS EKS deployment architecture for consistency and reliability.
