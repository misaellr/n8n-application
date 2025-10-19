# Azure AKS Deployment

Quick guide to deploy n8n on Azure Kubernetes Service using the automated setup CLI.

## What Gets Deployed

- **Infrastructure**: VNet, AKS cluster, managed node pool, NAT gateway
- **Networking**: Azure Load Balancer with configurable Public IP (static or dynamic)
- **Storage**: Azure Disk CSI driver with Premium SSD
- **Database**: SQLite (default) or Azure Database for PostgreSQL
- **Secrets**: Azure Key Vault
- **TLS**: Optional cert-manager with Let's Encrypt

## Prerequisites

```bash
# Required tools
python3 --version  # >= 3.8
terraform --version  # >= 1.6
kubectl version --client
helm version
az --version  # >= 2.50

# Azure login
az login
az account set --subscription "<subscription-id>"
az account show
```

See [Requirements](../reference/requirements.md) for installation instructions.

## Permissions

⚠️ **Important**: Azure requires specific RBAC permissions.

See [Azure Permissions Guide](../guides/azure-permissions.md) for detailed setup.

Quick check:
```bash
# Verify you have necessary permissions
az role assignment list --assignee $(az account show --query user.name -o tsv) \
  --query "[].roleDefinitionName" -o tsv
```

## Deploy

```bash
# Run interactive setup
python3 setup.py

# Follow prompts:
# 1. Cloud provider: azure
# 2. Azure subscription & location
# 3. Cluster configuration (or use defaults)
# 4. Database: SQLite or PostgreSQL
# 5. Static or dynamic IP for Load Balancer
# 6. Confirm and deploy
```

**Deployment time**: ~20 minutes

## What Happens

### Phase 1: Infrastructure (~15 min)
- Terraform creates VNet, AKS cluster, node pool
- Installs ingress-nginx controller (Azure LB)
- Creates Key Vault and stores encryption key

### Phase 2: Application (~2 min)
- Deploys n8n via Helm
- Configures database connection
- Sets up ingress routing

### Phase 3: Access (~1 min)
- Retrieves LoadBalancer IP
- Displays access information

### Phase 4: TLS (Optional, ~5 min)
- Configure DNS
- Install cert-manager
- Issue Let's Encrypt certificate

## Access Your Deployment

```bash
# Get LoadBalancer IP
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Check n8n status
kubectl get pods -n n8n
kubectl logs -f deployment/n8n -n n8n
```

## Configure DNS

```bash
# Get Public IP
LB_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Create A record
# n8n.yourdomain.com -> $LB_IP
```

## Enable HTTPS

After configuring DNS:

```bash
# Re-run setup and select TLS configuration
python3 setup.py

# Or configure manually:
helm upgrade n8n ./helm -n n8n --reuse-values \
  --set ingress.tls.enabled=true \
  --set ingress.annotations."cert-manager\.io/cluster-issuer"=letsencrypt-production
```

## Resource Management

| Resource | Management | Notes |
|----------|------------|-------|
| NAT Gateway Public IP | Terraform | 1 Public IP for outbound traffic |
| Load Balancer IP | Configurable | Static (Terraform) or Dynamic (Azure) |
| VNet, AKS, PostgreSQL | Terraform | In terraform state |

**Static IP Option**: Set `use_static_ip = true` in terraform.tfvars for consistent IP.

## Cost Estimate

**Default Configuration (East US, SQLite)**:
- AKS Control Plane: Free
- Standard_B2s node: $30/month
- NAT Gateway: $33/month
- Load Balancer: $18/month
- **Total: ~$81/month**

**With PostgreSQL**: Add $15-60/month for Azure Database

## Configuration Options

Edit `terraform.tfvars` or use CLI prompts:

```hcl
# Cluster
cluster_name = "n8n-aks-cluster"
node_vm_size = "Standard_B2s"
node_count = 1

# Database
database_type = "sqlite"  # or "postgresql"

# Networking
enable_nginx_ingress = true
use_static_ip = true  # or false for dynamic
vnet_cidr = "10.0.0.0/16"

# n8n
n8n_host = "n8n.yourdomain.com"
n8n_protocol = "https"
```

## Troubleshooting

### Permission Errors
```bash
# Verify subscription
az account show

# Check role assignments
az role assignment list --assignee $(az account show --query user.name -o tsv)
```

See [Azure Permissions Guide](../guides/azure-permissions.md) for common issues.

### Deployment Failures
```bash
# Check Terraform state
cd terraform/azure
terraform state list
terraform plan

# View setup history
cat setup_history.log

# Re-run deployment
python3 setup.py
```

### Access Issues
```bash
# Check ingress controller
kubectl get pods -n ingress-nginx
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx

# Check n8n
kubectl get all -n n8n
kubectl describe pod -n n8n -l app=n8n
kubectl logs -f deployment/n8n -n n8n
```

### Certificate Issues
```bash
# Check cert-manager
kubectl get certificate -n n8n
kubectl describe certificate n8n-tls -n n8n
kubectl get certificaterequest -n n8n
kubectl get challenge -n n8n
```

## Cleanup

```bash
# Delete all resources
python3 setup.py --teardown

# Or manually
cd terraform/azure
terraform destroy
```

## Known Issues

### Network Contributor Role
If using static IP, AKS needs Network Contributor role. The setup script configures this automatically, but you may encounter delays while the role propagates (1-2 minutes).

### Resource Provider Registration
First-time Azure users may need to register resource providers:
```bash
az provider register --namespace Microsoft.ContainerService
az provider register --namespace Microsoft.Network
az provider register --namespace Microsoft.KeyVault
az provider register --namespace Microsoft.DBforPostgreSQL
```

## Next Steps

- [Enable Basic Auth](../guides/configuration-history.md)
- [Configure Backups](#)
- [Set up Monitoring](#)
- [Scale Cluster](#)

## Support

- [Requirements](../reference/requirements.md)
- [Azure Permissions Guide](../guides/azure-permissions.md)
- [Configuration History](../guides/configuration-history.md)
- GitHub Issues
