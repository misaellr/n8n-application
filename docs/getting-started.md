# Getting Started

Quick start guide for deploying n8n on Kubernetes using this automation.

## Prerequisites

Before you begin, ensure you have:

- **Cloud Provider Account:** AWS or Azure with appropriate permissions
- **Required Tools:** See [requirements.md](reference/requirements.md) for installation instructions
  - Python 3.8+
  - Terraform >= 1.6
  - kubectl
  - Helm >= 3
  - Cloud CLI (AWS CLI or Azure CLI)

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd n8n-application
```

### 2. Run Setup

The interactive setup wizard will guide you through the deployment:

```bash
python setup.py
```

**What it does:**
1. Checks dependencies
2. Prompts for cloud provider (AWS or Azure)
3. Collects configuration (cluster size, region, database, etc.)
4. Saves configuration to `setup_history.log`
5. Deploys infrastructure with Terraform
6. Deploys n8n application with Helm

### 3. Access Your Deployment

After deployment completes, access n8n:

```bash
# Get the LoadBalancer URL
kubectl get svc -n ingress-nginx ingress-nginx-controller

# Access n8n at:
# http://<EXTERNAL-IP> or https://<your-domain>
```

## Cloud-Specific Guides

- **AWS EKS:** See [deployment/aws.md](deployment/aws.md)
- **Azure AKS:** See [deployment/azure.md](deployment/azure.md)

## Common Tasks

### View Configuration History

Every `setup.py` run is logged:

```bash
cat setup_history.log
```

See [configuration-history.md](guides/configuration-history.md) for details.

### Check Deployment Status

```bash
# Check pods
kubectl get pods -n n8n

# Check ingress
kubectl get ingress -n n8n

# View logs
kubectl logs -f deployment/n8n -n n8n
```

### Teardown Resources

```bash
python setup.py --teardown
```

## Troubleshooting

### Permission Issues

- **AWS**: See [aws-permissions.md](guides/aws-permissions.md)
- **Azure**: See [azure-permissions.md](guides/azure-permissions.md)

### Terraform State Issues

Configuration is saved to `setup_history.log`. You can:
- Re-run `setup.py` (it will prompt for same parameters)
- Or run `terraform apply` directly from `terraform/aws/` or `terraform/azure/`

### Continue After Failure

Your infrastructure is preserved in Terraform state. You can:
- Fix the issue
- Run `terraform apply` again (no need to re-run setup.py)

## Next Steps

- Configure TLS/HTTPS for production
- Set up backups
- Configure monitoring
- Review security settings

See the [deployment guides](deployment/) for detailed instructions.
