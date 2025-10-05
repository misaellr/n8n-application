# N8N Deployment Automation

Automated deployment setup for n8n workflow automation platform on AWS using Terraform (EC2) or Helm (EKS/Kubernetes).

## Features

- 🚀 **Interactive CLI Setup** - Guided configuration prompts for all deployment options
- ✅ **Dependency Checking** - Automatically verifies required tools are installed
- 🔐 **AWS Authentication** - Validates AWS credentials before deployment
- 🔄 **Idempotent Operations** - Safe to interrupt; changes only applied after full configuration
- 📦 **Dual Deployment Modes** - EC2 (simple) or EKS (scalable Kubernetes)
- 🔒 **Secure Configuration** - Handles encryption keys and sensitive data securely
- ↩️ **Auto Rollback** - Restores previous configuration on errors or interruption

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

### Optional Tools (for EKS deployment)

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
   - Choose deployment mode (EC2 or EKS)
   - Select AWS profile and region
   - Configure n8n settings (domain, timezone, etc.)
   - Review configuration summary
   - Confirm to proceed

4. **Wait for deployment**
   - The script will automatically run Terraform/Helm
   - For EC2: Creates EC2 instance, security groups, and deploys n8n
   - For EKS: Deploys n8n to your Kubernetes cluster

## Deployment Modes

### EC2 Mode (Recommended for Simple Deployments)

**What it creates:**
- EC2 instance with Docker and Docker Compose
- n8n container with Caddy reverse proxy
- Security group (ports 80/443)
- Elastic IP for stable public access
- SSM Parameter Store for encryption key
- IAM role for SSM access

**Configuration options:**
- AWS Region
- Instance Type (t3.micro, t3.small, t3.medium, etc.)
- Domain name (optional, for HTTPS via Caddy)
- Timezone
- n8n encryption key (auto-generated or provide your own)

**Access:**
- With domain: `https://your-domain.com`
- Without domain: `http://<elastic-ip>`

### EKS Mode (For Production/Scalable Deployments)

**Prerequisites:**
- Existing EKS cluster
- kubectl configured to access cluster
- Ingress controller installed (nginx-ingress recommended)
- cert-manager (optional, for TLS certificates)

**What it creates:**
- Kubernetes Deployment for n8n
- Service (ClusterIP)
- Ingress resource with TLS
- PersistentVolumeClaim for data storage
- Secret for sensitive configuration
- Optional HPA (Horizontal Pod Autoscaler)

**Configuration options:**
- N8N host (FQDN)
- Timezone
- Resource limits (CPU/Memory)
- Encryption key
- Database configuration (optional PostgreSQL)

## Configuration Files

The setup script modifies these files based on your inputs:

### For EC2 Deployment

- `terraform/variables.tf` - Variable defaults
- `terraform/terraform.tfvars` - Actual configuration values (created)

### For EKS Deployment

- `helm/values.yaml` - Helm chart configuration

**Note:** Original files are backed up before modification. If setup is interrupted, backups are automatically restored.

## Interrupting the Setup

You can safely interrupt the setup at any time:

- Press `Ctrl+C` during prompts
- The script will restore original configuration files
- No changes are applied until you confirm the configuration summary

## Post-Deployment

### EC2 Deployment

After successful deployment, you'll see:

```
🎉 Deployment Complete!
============================================================

N8N URL: http://XX.XX.XX.XX or https://your-domain.com
Elastic IP: XX.XX.XX.XX
Instance ID: i-xxxxxxxxxxxxx
```

**First-time setup:**
1. Open the N8N URL in your browser
2. Create your admin account
3. Start building workflows!

**SSH Access (via SSM):**
```bash
aws ssm start-session --target <instance-id> --profile <your-profile>
```

**View logs:**
```bash
aws ssm start-session --target <instance-id> --profile <your-profile>
# Then in the session:
cd /opt/n8n
docker-compose logs -f
```

### EKS Deployment

Check deployment status:

```bash
kubectl get pods -n default
kubectl get ingress -n default
kubectl get svc -n default
```

View logs:
```bash
kubectl logs -f deployment/n8n -n default
```

## Manual Deployment (Without Setup Script)

### EC2 via Terraform

```bash
cd terraform

# Initialize
terraform init

# Review changes
terraform plan

# Apply
terraform apply

# Get outputs
terraform output
```

### EKS via Helm

```bash
cd helm

# Edit values.yaml with your configuration
# At minimum, update:
# - ingress.host
# - env.N8N_HOST
# - env.WEBHOOK_URL
# - envSecrets.N8N_ENCRYPTION_KEY

# Install
helm install n8n . --namespace default --create-namespace

# Check status
helm status n8n -n default
```

## Configuration Reference

### Terraform Variables (terraform/variables.tf)

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_profile` | cloud-native-misael | AWS CLI profile |
| `region` | us-east-1 | AWS region |
| `instance_type` | t3.small | EC2 instance type |
| `domain` | "" | Optional domain for HTTPS |
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

### EC2 Deployment Issues

**Instance not accessible**
- Check security group rules (ports 80/443)
- Verify Elastic IP association
- Check instance status in AWS Console

**n8n not running**
- SSH into instance via SSM
- Check Docker status: `systemctl status docker`
- Check containers: `cd /opt/n8n && docker-compose ps`
- View logs: `docker-compose logs`

### EKS Deployment Issues

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
   - EC2: Uses AWS SSM Parameter Store
   - EKS: Uses Kubernetes Secrets (consider external-secrets-operator for production)

5. **Network Security**:
   - EC2: Security group restricts access to ports 80/443
   - EKS: Use network policies to restrict pod communication

6. **HTTPS**:
   - EC2: Caddy auto-provisions Let's Encrypt certificates when domain is configured
   - EKS: Use cert-manager with Let's Encrypt

## Cleanup

### EC2 Deployment

```bash
cd terraform
terraform destroy
```

This will remove:
- EC2 instance
- Elastic IP
- Security group
- IAM roles and policies
- SSM parameters

### EKS Deployment

```bash
helm uninstall n8n -n default
kubectl delete pvc n8n-data -n default
```

## Cost Estimation

### EC2 Deployment (us-east-1)

- t3.micro: ~$7/month
- t3.small: ~$15/month
- t3.medium: ~$30/month
- Elastic IP: Free while associated
- Data transfer: Varies by usage

### EKS Deployment

- EKS cluster: ~$73/month
- Worker nodes: Varies by instance type
- EBS volumes: ~$0.10/GB/month
- Load balancer: ~$16/month

## Advanced Configuration

### Using PostgreSQL (EKS)

Edit `helm/values.yaml`:

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

### Enabling HPA (EKS)

Edit `helm/values.yaml`:

```yaml
hpa:
  enabled: true
  minReplicas: 2
  maxReplicas: 5
  targetCPUUtilizationPercentage: 70
```

### Custom Domain with Route53 (EC2)

After deployment:

1. Get Elastic IP from Terraform output
2. Create Route53 A record pointing to Elastic IP
3. Re-run setup with domain configured
4. Caddy will automatically provision SSL certificate

## Support

- n8n Documentation: https://docs.n8n.io/
- Terraform AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Helm Documentation: https://helm.sh/docs/

## License

This deployment configuration is provided as-is for deploying n8n.
