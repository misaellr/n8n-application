# N8N EKS Deployment Automation

Automated deployment setup for n8n workflow automation platform on AWS EKS (Kubernetes) using Terraform and Helm.

## Features

- 🚀 **Interactive CLI Setup** - Guided configuration prompts for EKS deployment
- ✅ **Dependency Checking** - Automatically verifies required tools are installed
- 🔐 **AWS Authentication** - Validates AWS credentials before deployment
- 🔄 **Idempotent Operations** - Safe to interrupt; changes only applied after full configuration
- ☸️ **Production-Ready EKS** - Multi-AZ, highly available Kubernetes cluster
- 🔒 **Secure Configuration** - Handles encryption keys and sensitive data securely
- ↩️ **Auto Rollback** - Restores previous configuration on errors or interruption
- 📊 **Complete Infrastructure** - VPC, networking, storage, ingress all automated

## Prerequisites

### Required Tools

1. **Terraform** (>= 1.6)
   ```bash
   # Install on Linux
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install terraform
   ```

2. **AWS CLI** (>= 2.0)
   ```bash
   # Install on Linux
   curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
   unzip awscliv2.zip
   sudo ./aws/install
   ```

3. **Python 3** (>= 3.7) - Usually pre-installed on most systems

4. **Helm** (>= 3.0)
   ```bash
   curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
   ```

5. **kubectl**
   ```bash
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
   ```

### AWS Configuration

Configure AWS credentials before running the setup:

```bash
aws configure --profile <your-profile-name>
```

You'll need:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., us-east-1)
- Output format (json recommended)

## Quick Start

1. **Clone or navigate to the repository**
   ```bash
   cd n8n-application
   ```

2. **Run the setup script**
   ```bash
   python3 setup.py
   ```

3. **Follow the interactive prompts**
   - Select AWS profile and region
   - Configure EKS cluster settings (name, node types, sizing)
   - Configure n8n settings (hostname, timezone, storage, etc.)
   - Review configuration summary
   - Confirm to proceed

4. **Wait for deployment** (~25-30 minutes)
   - The script will automatically run Terraform and Helm
   - Creates VPC, EKS cluster, node group, and all networking
   - Deploys n8n via Helm chart with ingress

## What Gets Deployed

**Infrastructure (via Terraform):**
- VPC with public/private subnets across 3 Availability Zones
- NAT Gateways (3x) for private subnet internet access
- Internet Gateway for public subnet access
- EKS cluster (Kubernetes 1.31) with managed control plane
- EKS node group (2x t3.medium instances by default) in private subnets
- EBS CSI driver addon for persistent storage
- Default StorageClass (gp3, encrypted)
- NGINX Ingress Controller with Network Load Balancer
- IAM roles and policies (cluster, nodes, IRSA for EBS CSI)
- SSM Parameter Store for n8n encryption key (SecureString)

**Application (via Helm):**
- N8N deployment with configurable resources
- PersistentVolumeClaim (10Gi by default) for data storage
- Kubernetes Service (ClusterIP)
- Ingress resource for external access
- Kubernetes Secret for encryption key
- Optional: Horizontal Pod Autoscaler

**Configuration options:**
- AWS Region
- EKS cluster name
- Node instance types (t3.small, t3.medium, t3.large)
- Node group sizing (min/desired/max)
- N8N hostname (FQDN) - required
- Kubernetes namespace (default: n8n)
- Storage size (default: 10Gi)
- Timezone
- n8n encryption key (auto-generated or provide your own)

**Access:**
- Via ingress hostname: `https://your-hostname.com` (requires DNS configuration)

## Configuration Files

The setup script modifies these files based on your inputs:

- `terraform/terraform.tfvars` - Terraform configuration values (created by setup script)
- Terraform reads default values from `terraform/variables.tf`
- Helm reads configuration from `helm/values.yaml` and Terraform provides overrides

**Note:** Original files are backed up before modification. If setup is interrupted, backups are automatically restored.

## Interrupting the Setup

You can safely interrupt the setup at any time:

- Press `Ctrl+C` during prompts
- The script will restore original configuration files
- No changes are applied until you confirm the configuration summary

## Post-Deployment

Check deployment status:

```bash
kubectl get pods -n n8n
kubectl get ingress -n n8n
kubectl get svc -n ingress-nginx
```

View logs:
```bash
kubectl logs -f deployment/n8n -n n8n
```

**Note**: Replace `-n n8n` with your configured namespace if different.

## Manual Deployment (Without Setup Script)

If you prefer to run Terraform and Helm manually:

```bash
cd terraform

# Create terraform.tfvars with your configuration
# See terraform/variables.tf for available options

# Initialize
terraform init

# Review changes
terraform plan

# Apply (creates EKS cluster, VPC, networking, and deploys n8n via Helm)
terraform apply

# Get outputs (cluster name, endpoint, configure kubectl command)
terraform output
```

**Note:** Terraform automatically deploys n8n via the `helm_release` resource. You don't need to run `helm install` separately.

## Configuration Reference

### Terraform Variables (terraform/variables.tf)

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_profile` | Your AWS profile name | AWS CLI profile to use for deployment. |
| `region` | us-east-1 | AWS region |
| `cluster_name` | n8n-eks-cluster | EKS cluster name |
| `node_instance_types` | ["t3.medium"] | Node instance types |
| `node_desired_size` | 2 | Desired number of nodes |
| `node_min_size` | 1 | Minimum number of nodes |
| `node_max_size` | 3 | Maximum number of nodes |
| `n8n_host` | n8n.lrproduhub.com | N8N ingress hostname (FQDN) |
| `n8n_namespace` | n8n | Kubernetes namespace |
| `timezone` | America/Bahia | Timezone for n8n |
| `n8n_encryption_key` | (generated) | 64-char hex encryption key |

### Helm Values (helm/values.yaml)

| Value | Default | Description |
|-------|---------|-------------|
| `image.tag` | latest | n8n Docker image tag |
| `replicaCount` | 1 | Number of replicas |
| `service.type` | ClusterIP | Kubernetes service type |
| `ingress.enabled` | true | Enable ingress |
| `ingress.host` | n8n.lrproduhub.com | Ingress hostname |
| `persistence.size` | 10Gi | PVC storage size |
| `resources.limits.memory` | 1Gi | Memory limit |
| `hpa.enabled` | false | Enable autoscaling |

## Troubleshooting

### Setup Script Issues

**"AWS authentication failed"**
- Run `aws configure --profile <profile-name>`
- Verify credentials with `aws sts get-caller-identity --profile <profile-name>`

**"Missing dependencies"**
- Install required tools as shown in Prerequisites
- Verify installation: `terraform version`, `aws --version`

**"Terraform init failed"**
- Check internet connectivity
- Verify Terraform is properly installed
- Try manual init: `cd terraform && terraform init`

### Deployment Issues

**Pods not starting**
```bash
kubectl describe pod <pod-name> -n default
kubectl logs <pod-name> -n default
```

**Ingress not working**
- Verify ingress controller is running
- Check ingress resource: `kubectl describe ingress n8n`
- Verify DNS points to load balancer

**PVC pending**
- Check storage class: `kubectl get sc`
- Ensure default storage class exists

## Security Considerations

1. **Encryption Key**: Store the generated encryption key securely. It's needed for data decryption.

2. **AWS Credentials**: Use IAM roles with minimal required permissions.

3. **Terraform State**: Store state in S3 with encryption and versioning for production.

4. **Secrets Management**:
   - Uses AWS SSM Parameter Store (SecureString) for n8n encryption key
   - Kubernetes Secrets for runtime secrets
   - Consider external-secrets-operator for production to sync from AWS Secrets Manager

5. **Network Security**:
   - All EKS nodes deployed in private subnets
   - Security groups restrict access appropriately
   - Use Kubernetes Network Policies to restrict pod communication
   - Consider using AWS Security Groups for Pods

6. **HTTPS**:
   - Configure TLS termination at ingress level
   - Use cert-manager with Let's Encrypt for automatic certificate management
   - Or terminate TLS at ALB/NLB level with ACM certificates

## Cleanup

### Automated Teardown (Recommended)

```bash
python3 setup.py --teardown
```

This automated teardown will:
- Uninstall all Helm releases (n8n, ingress-nginx, cert-manager)
- Delete Kubernetes resources (PVCs, secrets, namespaces)
- Destroy Terraform infrastructure (EKS, VPC, RDS, etc.)
- Clean up AWS Secrets Manager entries (with confirmation)
- Automatically detect and disable RDS deletion protection

**Total time**: ~10-20 minutes

**Safety features**:
- Double confirmation required
- 5-second countdown before execution
- Graceful handling of missing resources

### Manual Cleanup

```bash
cd terraform
terraform destroy
```

**Note**: Manual cleanup requires additional steps to remove Helm releases first:

```bash
helm uninstall n8n -n n8n
helm uninstall cert-manager -n cert-manager  # if installed
kubectl delete namespace n8n cert-manager ingress-nginx
```

This will remove all resources:
- EKS cluster and node group
- VPC, subnets, NAT gateways, Internet gateway
- Network Load Balancer
- IAM roles and policies
- SSM parameters
- RDS instance (if created)
- PersistentVolumeClaims and EBS volumes

## Cost Estimation

### EKS Deployment (us-east-1)

- EKS control plane: ~$73/month
- EC2 nodes (2x t3.medium): ~$60/month
- NAT Gateways (3x): ~$97/month
- Network Load Balancer: ~$16/month
- EBS volumes (10Gi): ~$1/month
- Data transfer: Varies by usage (~$5-10/month)
- **Total: ~$252-262/month**

**Cost optimization options:**
- Use 1 NAT Gateway instead of 3 (saves ~$65/month, reduces HA)
- Use t3.small nodes (saves ~$30/month)
- Reduce node count to 1 (saves ~$30/month, reduces HA)

## Advanced Configuration

### Redeploying Application Only

If infrastructure is already deployed and you want to update just the n8n application (without redeploying EKS, VPC, etc.):

```bash
python3 setup.py --skip-terraform
```

This skips Phase 1 (Terraform infrastructure) and starts directly from Phase 2 (Helm deployment).

**Use cases**:
- Redeploying n8n after infrastructure is already up
- Testing Helm chart changes without rerunning Terraform
- Recovering from failed application deployments
- Updating n8n configuration without touching infrastructure

**Requirements**:
- Infrastructure must already be deployed (terraform.tfstate must exist)
- Existing terraform.tfvars will be loaded automatically
- kubectl context will be configured automatically

### Using PostgreSQL

You can configure n8n to use PostgreSQL instead of SQLite by editing `helm/values.yaml`:

```yaml
envSecrets:
  N8N_ENCRYPTION_KEY: "<your-key>"
  DB_TYPE: "postgresdb"
  DB_POSTGRESDB_HOST: "<rds-endpoint>"
  DB_POSTGRESDB_PORT: "5432"
  DB_POSTGRESDB_DATABASE: "n8n"
  DB_POSTGRESDB_USER: "n8nuser"
  DB_POSTGRESDB_PASSWORD: "<password>"
```

### Enabling HPA (Horizontal Pod Autoscaler)

Edit `helm/values.yaml`:

```yaml
hpa:
  enabled: true
  minReplicas: 2
  maxReplicas: 5
  targetCPUUtilizationPercentage: 70
```

### Custom Domain with Route53

After deployment:

1. Get Network Load Balancer DNS from Terraform output or via:
   ```bash
   kubectl get ingress n8n -n n8n
   ```
2. Create Route53 CNAME or ALIAS record pointing to the NLB DNS
3. Wait for DNS propagation (5-30 minutes)
4. Access n8n via your custom domain

## Support

- n8n Documentation: https://docs.n8n.io/
- Terraform AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Helm Documentation: https://helm.sh/docs/

## License

This deployment configuration is provided as-is for deploying n8n.
