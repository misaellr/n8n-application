# Requirements

## Prerequisites

### Required Tools
- Python 3.8+
- Terraform >= 1.6
- kubectl
- Helm >= 3
- AWS CLI >= 2.0 or Azure CLI >= 2.50

### Cloud Accounts
- **AWS**: Active AWS account with permissions to create VPC, EKS, IAM, RDS
- **Azure**: Active Azure subscription with permissions to create VNet, AKS, Key Vault

## Installation

### macOS
```bash
# Homebrew
brew install python terraform kubectl helm awscli
# or
brew install python terraform kubectl helm azure-cli
```

### Linux (Ubuntu/Debian)
```bash
# Terraform
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

## Cloud Setup

### AWS
```bash
aws configure --profile <profile-name>
# Enter: Access Key ID, Secret Access Key, Region
```

### Azure
```bash
az login
az account set --subscription "<subscription-id>"
```

## Permissions

### AWS IAM Permissions Required
- VPC, Subnet, Internet Gateway, NAT Gateway
- EKS Cluster and Node Groups
- EC2 (Security Groups, Route Tables)
- IAM (Roles, Policies)
- EBS (for persistent volumes)
- Systems Manager Parameter Store
- Secrets Manager
- RDS (if using PostgreSQL)

### Azure RBAC Permissions Required
- Virtual Network, Subnets, NAT Gateway
- AKS Cluster
- Key Vault
- Managed Identity
- Azure Database for PostgreSQL (if using)

See [Azure Permissions Guide](../guides/azure-permissions.md) for detailed Azure setup.

## Quick Start

```bash
# Clone repository
git clone <repo-url>
cd n8n-application

# Run setup
python3 setup.py

# Follow prompts to configure and deploy
```

## Cost Estimates

### AWS (us-east-1, SQLite)
- EKS Control Plane: ~$73/month
- t3.medium worker node: ~$30/month
- NAT Gateway: ~$33/month
- NLB: ~$16/month
- **Total: ~$157/month**

### Azure (East US, SQLite)
- AKS Control Plane: Free
- Standard_B2s worker node: ~$30/month
- NAT Gateway: ~$33/month
- Load Balancer: ~$18/month
- **Total: ~$81/month**

Add ~$15-60/month for PostgreSQL if selected.

## Troubleshooting

### AWS Permission Errors
```bash
# Verify credentials
aws sts get-caller-identity --profile <profile>
```

### Azure Permission Errors
See [Azure Permissions Guide](../guides/azure-permissions.md)

### Deployment Failures
1. Check `setup_history.log` for configuration
2. Review Terraform state: `cd terraform/{aws|azure} && terraform state list`
3. Re-run: `python3 setup.py`

### Access Issues
```bash
# Get LoadBalancer endpoint
kubectl get svc -n ingress-nginx

# Check pod status
kubectl get pods -n n8n

# View logs
kubectl logs -f deployment/n8n -n n8n
```

## Support

- **Documentation**: See `docs/` directory
- **Issues**: GitHub Issues
- **Configuration History**: `setup_history.log`
