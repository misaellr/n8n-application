# N8N EKS Deployment Guide

## Overview
- Terraform provisions a dedicated VPC (three public and three private subnets), Internet/NAT gateways, an Amazon EKS 1.29 control plane, and a managed node group sized by `node_*` variables.
- AWS IAM roles are created for the control plane, worker nodes, and the AWS EBS CSI driver; the driver is enabled with a default `ebs-gp3` StorageClass.
- Sensitive settings (the n8n encryption key, database credentials, basic auth credentials) are stored in AWS Systems Manager Parameter Store and AWS Secrets Manager, then injected into Kubernetes Secrets at deploy time.
- Terraform installs the upstream `ingress-nginx` chart (Network Load Balancer with static Elastic IPs by default) but **does NOT deploy n8n**. The n8n application is deployed separately via Helm CLI by `setup.py` after infrastructure is ready.
- Database backend can be SQLite (default, file-based) or PostgreSQL (RDS). The CLI prompts for database selection and provisions RDS resources if PostgreSQL is chosen.
- TLS/HTTPS configuration is handled as a **post-deployment step** after the LoadBalancer is provisioned and DNS can be configured. This prevents race conditions with Let's Encrypt validation.
- Basic authentication can be configured post-deployment to protect access to n8n with auto-generated credentials (stored in AWS Secrets Manager).
- The interactive CLI (`python3 setup.py`) orchestrates a **4-phase deployment**: (1) Terraform infrastructure, (2) n8n application via Helm, (3) LoadBalancer retrieval, (4) optional TLS & Basic Auth configuration.

## Prerequisites
- macOS or Linux workstation with `python3`, Terraform >= 1.6, AWS CLI >= 2.0, kubectl, and Helm >= 3. The CLI verifies these before continuing.
- AWS credentials with permissions to create VPC, EC2, EKS, IAM, SSM, and load-balancer resources. Configure them with `aws configure --profile <profile>`.
- Optional: a DNS hostname if you plan to front n8n with TLS. Without a hostname the deployment still completes and you can use the load balancer DNS name.

## Deploy with the Setup CLI

The setup CLI performs a **4-phase deployment** to avoid race conditions with TLS certificate issuance:

### Phase 1: Infrastructure Deployment (~22-27 minutes)
1. From the repository root, run `python3 setup.py`.
2. Follow the prompts for:
   - AWS profile/region
   - Cluster sizing (node instance type, min/desired/max counts)
   - Kubernetes namespace (default: n8n)
   - Storage size for PVC (default: 10Gi)
   - Hostname and timezone
   - **Database selection**: SQLite (file-based, ~$1/month) or PostgreSQL/RDS (~$15-60/month)
     - If PostgreSQL: prompts for RDS instance class, storage size, and multi-AZ configuration
   - Encryption key (leaving blank generates a secure 64-character key)
   - **Note**: TLS and Basic Auth configuration are NOT requested during this phase.
3. The CLI displays the Terraform plan summary and asks for confirmation before proceeding.
4. The CLI writes `terraform/terraform.tfvars`, then runs `terraform init`, `terraform plan`, and `terraform apply`.
5. Terraform provisions:
   - VPC, subnets, NAT gateways, Internet Gateway
   - EKS cluster and managed node group
   - NGINX ingress controller (creates Network Load Balancer with static Elastic IPs)
   - EBS CSI driver and default StorageClass
   - SSM Parameter for encryption key
   - **If PostgreSQL selected**: RDS instance, database security group, credentials in Secrets Manager

### Phase 2: Application Deployment (~2-3 minutes)
6. After Terraform completes, the CLI configures kubectl using the `configure_kubectl` output.
7. **If PostgreSQL was selected**: The CLI creates a Kubernetes Secret with the database password (retrieved from Terraform outputs).
8. The CLI deploys n8n via **Helm CLI** (not Terraform):
   ```bash
   helm install n8n ./helm -n <namespace> --create-namespace \
     --set ingress.enabled=true \
     --set ingress.className=nginx \
     --set ingress.host=<your-hostname> \
     --set ingress.tls.enabled=false \
     --set env.N8N_PROTOCOL=http \
     --set persistence.size=<configured-size> \
     --set-string envSecrets.N8N_ENCRYPTION_KEY=<from-ssm> \
     --set database.type=<sqlite|postgresql> \
     --set database.postgresql.host=<rds-address>  # if PostgreSQL
   ```
9. The application is initially deployed with **HTTP only** (no TLS).
10. The CLI waits for the deployment to be ready (`kubectl wait --for=condition=available deployment/n8n` with 5-minute timeout).

### Phase 3: LoadBalancer Retrieval (~1-2 minutes)
11. The CLI polls for the LoadBalancer DNS name:
    ```bash
    kubectl get svc -n ingress-nginx ingress-nginx-controller \
      -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
    ```
12. Once ready, the LoadBalancer URL and **static Elastic IPs** are displayed:
    ```
    LoadBalancer URL:  a1234567890.us-east-1.elb.amazonaws.com
    Static Elastic IPs: 52.1.2.3, 52.1.2.4, 52.1.2.5
    Access n8n at:     http://a1234567890.us-east-1.elb.amazonaws.com
    ```
    The static IPs allow for consistent DNS A-record mapping.

### Phase 4: TLS Configuration (Optional, ~5 minutes)
10. The CLI prompts: **"Would you like to configure TLS/HTTPS now?"**
11. If you choose **Yes**, select one of two options:
    - **Bring Your Own Certificate**: Provide PEM certificate and key files
    - **Let's Encrypt**: Automated certificate via HTTP-01 validation

#### Let's Encrypt Flow:
12. The CLI displays the actual LoadBalancer URL and prompts:
    ```
    ⚠️  IMPORTANT - DNS Configuration Required
    1. Create DNS record for: your-domain.com
    2. Point to LoadBalancer: a1234567890.us-east-1.elb.amazonaws.com

    Have you configured the DNS record? [y/N]
    ```
13. You **must confirm DNS is configured** before proceeding.
14. The CLI then:
    - Installs cert-manager via Helm
    - Creates a ClusterIssuer for Let's Encrypt
    - Upgrades n8n Helm release with TLS enabled and cert-manager annotations
15. Let's Encrypt validates ownership via HTTP-01 challenge and issues the certificate (~2-5 minutes).
16. Once the certificate is ready, access n8n at `https://your-domain.com`.

#### BYO Certificate Flow:
12. The CLI prompts for certificate and key PEM files.
13. The CLI creates a Kubernetes TLS secret:
    ```bash
    kubectl create secret tls n8n-tls -n n8n \
      --cert=path/to/cert.pem \
      --key=path/to/key.pem
    ```
14. The CLI upgrades n8n Helm release with TLS enabled.
15. Access n8n at `https://your-domain.com`.

### Phase 4b: Basic Authentication Configuration (Optional, ~1 minute)
16. After TLS configuration (or if TLS is skipped), the CLI prompts: **"Would you like to enable basic authentication for n8n?"**
17. If you choose **Yes**:
    - The CLI auto-generates credentials:
      - Username: `admin`
      - Password: 12 random alphanumeric characters
    - Credentials are stored in AWS Secrets Manager at `/n8n/basic-auth`
    - Credentials are displayed to the user (you **must save them**)
    - The CLI creates a Kubernetes Secret with bcrypt-hashed password:
      ```bash
      kubectl create secret generic n8n-basic-auth -n <namespace> \
        --from-literal=auth='admin:<bcrypt-hash>'
      ```
    - The CLI upgrades n8n Helm release with basic auth annotations:
      ```bash
      helm upgrade n8n ./helm -n <namespace> \
        --reuse-values \
        --set ingress.basicAuth.enabled=true \
        --set ingress.basicAuth.secretName=n8n-basic-auth
      ```
18. Access to n8n now requires HTTP basic authentication before reaching the n8n login page.
19. Both HTTP and HTTPS traffic are protected by basic auth (if enabled).

**Security Notes**:
- Basic auth credentials are hashed using bcrypt (not SHA-1)
- Credentials are stored in AWS Secrets Manager for recovery
- Basic auth protects the ingress layer, independent of n8n's own authentication
- Requires `htpasswd` utility (from `apache2-utils` package on Debian/Ubuntu)

### Artifacts Created by the CLI
- `terraform/terraform.tfvars` containing infrastructure configuration (AWS profile, region, cluster sizing, database type, hostname, timezone, namespace, PVC size).
- A generated encryption key if you declined to supply one; the key is saved in Parameter Store at `/n8n/encryption_key`.
- Helm release `n8n` in the configured namespace (deployed via Helm CLI, not Terraform).
- **If PostgreSQL selected**: Kubernetes Secret `n8n-db-credentials` containing database password.
- **If PostgreSQL selected**: AWS Secrets Manager secret with RDS credentials.
- Optional: cert-manager installation and ClusterIssuer (if Let's Encrypt TLS was configured).
- Optional: Kubernetes TLS secret `n8n-tls` (if BYO certificate was provided).
- Optional: Kubernetes Secret `n8n-basic-auth` with bcrypt-hashed credentials (if basic auth was configured).
- Optional: AWS Secrets Manager secret at `/n8n/basic-auth` (if basic auth was configured).
- No changes are made to Terraform module defaults or `helm/values.yaml`; all overrides are passed via CLI arguments.

## Manual Command Reference

If you prefer to run the deployment manually (without `setup.py`), follow these steps:

### Step 1: Deploy Infrastructure with Terraform
```bash
# Create terraform/terraform.tfvars with required values:
# aws_profile, region, n8n_host, and optionally n8n_encryption_key

terraform fmt terraform/
(cd terraform && terraform init)
(cd terraform && terraform validate)
(cd terraform && terraform plan -out plan.out)
(cd terraform && terraform apply plan.out)

# Configure kubectl
$(cd terraform && terraform output -raw configure_kubectl)
```

### Step 2: Deploy n8n with Helm
```bash
# Get encryption key from Terraform output
ENCRYPTION_KEY=$(cd terraform && terraform output -raw n8n_encryption_key_value)
N8N_HOST=$(cd terraform && terraform output -raw n8n_host)

# Lint and test the Helm chart
helm lint helm
helm template helm --values helm/values.yaml

# Deploy n8n (HTTP only initially)
helm install n8n ./helm -n n8n --create-namespace \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.host=$N8N_HOST \
  --set ingress.tls.enabled=false \
  --set env.N8N_HOST=$N8N_HOST \
  --set env.N8N_PROTOCOL=http \
  --set-string envSecrets.N8N_ENCRYPTION_KEY=$ENCRYPTION_KEY
```

### Step 3: Get LoadBalancer URL
```bash
# Wait for LoadBalancer to be ready
kubectl get svc -n ingress-nginx ingress-nginx-controller -w

# Get LoadBalancer URL
LB_URL=$(kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "Access n8n at: http://$LB_URL"
```

### Step 4: Configure TLS (Optional)

#### Option A: Let's Encrypt
```bash
# 1. Configure DNS to point your domain to $LB_URL

# 2. Install cert-manager
helm install cert-manager https://charts.jetstack.io/charts/cert-manager-v1.13.3.tgz \
  --namespace cert-manager --create-namespace --set installCRDs=true

# 3. Create ClusterIssuer (example for production)
kubectl apply -f - <<EOF
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

# 4. Upgrade n8n with TLS enabled
helm upgrade n8n ./helm -n n8n \
  --reuse-values \
  --set ingress.tls.enabled=true \
  --set env.N8N_PROTOCOL=https \
  --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt-production'

# 5. Watch certificate issuance
kubectl get certificate -n n8n -w
```

#### Option B: Bring Your Own Certificate
```bash
# 1. Create TLS secret from your certificate files
kubectl create secret tls n8n-tls -n n8n \
  --cert=path/to/cert.pem \
  --key=path/to/key.pem

# 2. Upgrade n8n with TLS enabled
helm upgrade n8n ./helm -n n8n \
  --reuse-values \
  --set ingress.tls.enabled=true \
  --set env.N8N_PROTOCOL=https
```

## Configuration Reference
- **Identity & Networking**
  - `aws_profile`, `region`, and `project_tag` set naming and tagging for all resources.
  - `vpc_cidr` defaults to `10.0.0.0/16`; subnets and NAT gateways are created per availability zone returned by `data.aws_availability_zones.available` (first three AZs).
- **Cluster & Nodes**
  - `cluster_name` defaults to `n8n-eks-cluster`, Kubernetes version `1.29`.
  - Worker capacity is controlled via `node_instance_types`, `node_desired_size`, `node_min_size`, and `node_max_size`.
- **Ingress & TLS**
  - `enable_nginx_ingress` installs `ingress-nginx` backed by an AWS Network Load Balancer with static Elastic IPs.
  - When enabled, static Elastic IPs are allocated and attached to the NLB for consistent DNS A-record mapping.
  - TLS configuration is **not handled by Terraform**. The n8n application is initially deployed with HTTP only.
  - TLS is configured post-deployment via `setup.py` (Phase 4) or manually using Helm upgrade commands.
  - `n8n_ingress_annotations` can be extended (for example, ALB annotations) through `terraform.tfvars`.
- **Database Configuration**
  - `database_type` defaults to `sqlite` (file-based, no RDS costs). Set to `postgresql` to provision RDS.
  - `rds_instance_class`, `rds_allocated_storage`, `rds_multi_az` configure the PostgreSQL database when enabled.
  - `rds_database_name` and `rds_username` set the database name and master username.
  - Database credentials are auto-generated and stored in AWS Secrets Manager and Kubernetes Secrets (not in Helm values).
  - PostgreSQL provides production-grade scalability at additional cost (~$15-60/month for db.t3.micro to db.t3.small).
- **Basic Authentication**
  - `enable_basic_auth` defaults to `false`. When enabled, auto-generated credentials protect the ingress.
  - Credentials (username: `admin`, password: 12 random chars) stored in AWS Secrets Manager at `/n8n/basic-auth`.
  - Password hashed using bcrypt before storage in Kubernetes Secret `n8n-basic-auth`.
  - Basic auth is independent of n8n's own authentication and protects both HTTP and HTTPS access.
- **Application Settings**
  - `n8n_host` falls back to `<project_tag>.local` when left blank.
  - `n8n_namespace` defaults to `n8n`. All kubectl/helm operations honor the configured namespace.
  - `n8n_encryption_key` defaults to empty; Terraform automatically generates a secure key when none is supplied.
  - `n8n_persistence_size` defaults to `10Gi`. The configured size is passed to Helm during deployment.
  - Additional non-sensitive environment overrides can be added via `n8n_env_overrides`.

## TLS and DNS Scenarios

TLS configuration is a **post-deployment step** that occurs after the LoadBalancer is provisioned. This prevents race conditions with certificate validation.

### No TLS (Default Initial State)
- The n8n application is initially deployed with HTTP only.
- Access via the LoadBalancer DNS: `http://a1234567890.us-east-1.elb.amazonaws.com`
- Optionally create a CNAME/ALIAS to the LoadBalancer for friendly URLs.

### Bring Your Own Certificate
1. **After deployment**, create a Kubernetes TLS secret with your PEM-encoded certificate and key:
   ```bash
   kubectl create secret tls n8n-tls -n n8n \
     --cert=path/to/cert.pem \
     --key=path/to/key.pem
   ```
2. Upgrade the n8n Helm release to enable TLS:
   ```bash
   helm upgrade n8n ./helm -n n8n \
     --reuse-values \
     --set ingress.tls.enabled=true \
     --set env.N8N_PROTOCOL=https
   ```
3. Point your DNS to the LoadBalancer; traffic terminates with your certificate.

### Let's Encrypt
1. **After deployment**, configure DNS to point your hostname to the LoadBalancer DNS.
2. Verify DNS resolution: `nslookup your-domain.com` should return the LoadBalancer IP.
3. Install cert-manager:
   ```bash
   helm install cert-manager https://charts.jetstack.io/charts/cert-manager-v1.13.3.tgz \
     --namespace cert-manager --create-namespace --set installCRDs=true
   ```
4. Create a ClusterIssuer for Let's Encrypt (production or staging).
5. Upgrade n8n with TLS and cert-manager annotation:
   ```bash
   helm upgrade n8n ./helm -n n8n \
     --reuse-values \
     --set ingress.tls.enabled=true \
     --set env.N8N_PROTOCOL=https \
     --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt-production'
   ```
6. cert-manager performs HTTP-01 validation and issues the certificate (~2-5 minutes).
7. Certificates renew automatically before expiration.

## Post-Deployment Verification
```bash
# Configure kubectl (if the CLI was unable to run it automatically)
$(cd terraform && terraform output -raw configure_kubectl)

# Confirm cluster health
kubectl get nodes

# Check n8n deployment
kubectl get all -n n8n
kubectl get pvc -n n8n
kubectl get ingress -n n8n

# Check ingress controller
kubectl get all -n ingress-nginx

# Fetch the LoadBalancer hostname
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

# View n8n logs
kubectl logs -f deployment/n8n -n n8n
```
- Access n8n via the LoadBalancer URL (HTTP initially).
- If TLS was configured with Let's Encrypt, confirm certificate readiness: `kubectl get certificate -n n8n`
- Once certificate shows `READY=True`, access via HTTPS.

## Operational Tips
- **Logs**:
  - n8n: `kubectl logs -f deployment/n8n -n n8n`
  - Ingress: `kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller`
  - cert-manager (if installed): `kubectl logs -n cert-manager -l app=cert-manager`
- **Storage**: `kubectl get pvc -n n8n` ensures the PersistentVolume is bound to the gp3 StorageClass.
- **Helm Operations**:
  - List releases: `helm list -n n8n`
  - Show values: `helm get values n8n -n n8n`
  - Upgrade with new values: `helm upgrade n8n ./helm -n n8n --reuse-values --set key=value`
- **Scaling**:
  - Modify `replicaCount` in `helm/values.yaml` or use `--set replicaCount=3`
  - Enable HPA: `--set autoscaling.enabled=true`
  - Then run: `helm upgrade n8n ./helm -n n8n --reuse-values -f helm/values.yaml`

## Cost and Scaling Considerations

**Baseline monthly estimate in `us-east-1`:**
- EKS control plane: ~$73
- One `t3.medium` worker node: ~$30
- Three NAT gateways: ~$98
- Network Load Balancer: ~$16
- Three static Elastic IPs: ~$11
- gp3 volume (10GB): ~$1
- **SQLite deployment total: ~$229/month**
- **PostgreSQL deployment (db.t3.micro): ~$244/month** (add ~$15/month for RDS)
- **PostgreSQL deployment (db.t3.small): ~$259/month** (add ~$30/month for RDS)

**Cost optimization strategies:**
- Reduce AZ count (fewer NAT gateways and Elastic IPs)
- Use smaller instance types (t3.small for nodes)
- Single-AZ RDS (not recommended for production)
- Consider AWS VPC endpoints to reduce NAT gateway data transfer costs

**Scaling options:**
- Increase `node_max_size` for horizontal node scaling
- Enable Helm HPA for pod autoscaling
- Integrate Kubernetes Cluster Autoscaler (not included by default)

## Cleanup

To completely remove the deployment:

### Step 1: Uninstall Helm Releases
```bash
# Uninstall n8n
helm uninstall n8n -n n8n

# Uninstall cert-manager (if installed)
helm uninstall cert-manager -n cert-manager

# Delete namespaces
kubectl delete namespace n8n cert-manager
```

**Important**: Terraform will **not** automatically destroy Helm-deployed resources. You must uninstall them manually before running `terraform destroy`.

### Step 2: Destroy Infrastructure
```bash
cd terraform
terraform destroy
```

This removes:
- EKS cluster and node group
- VPC, subnets, NAT gateways, Internet Gateway
- IAM roles and policies
- SSM Parameter Store entry
- NGINX ingress controller (deployed by Terraform)

### Step 3: Clean Up External Resources
- Delete any DNS records you created for the deployment
- Remove any local state files if needed

## Further Reading
- N8N Documentation: https://docs.n8n.io/
- AWS EKS Best Practices: https://aws.github.io/aws-eks-best-practices/
- Terraform AWS Provider Docs: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Helm Documentation: https://helm.sh/docs/
