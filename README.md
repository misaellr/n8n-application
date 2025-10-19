# N8N Multi-Cloud Deployment Automation

Automated deployment of n8n workflow automation platform on Kubernetes (AWS EKS or Azure AKS) using Terraform and Helm.

## Features

- 🚀 **Interactive Setup** - Guided CLI wizard for configuration
- ☁️ **Multi-Cloud** - Deploy on AWS EKS or Azure AKS
- 🔐 **Secure by Default** - Secrets in Key Vault/Parameter Store
- ☸️ **Production-Ready** - HA cluster, auto-scaling, monitoring
- 📊 **Complete Infrastructure** - VPC/VNet, networking, storage, ingress
- ↩️ **Safe Deployments** - Auto-rollback on errors, configuration history

## Quick Start

```bash
# Run interactive setup
python setup.py
```

The setup wizard will:
1. Check dependencies
2. Guide you through configuration
3. Deploy infrastructure (Terraform)
4. Deploy n8n application (Helm)
5. Provide access URL

**That's it!** Your n8n instance will be running on Kubernetes.

## Documentation

- **[Getting Started](docs/getting-started.md)** - Quick start guide
- **Deployment Guides:**
  - [AWS EKS Deployment](docs/deployment/aws.md)
  - [Azure AKS Deployment](docs/deployment/azure.md)
- **Guides:**
  - [Azure Permissions](docs/guides/azure-permissions.md)
  - [Configuration History](docs/guides/configuration-history.md)
- **Reference:**
  - [Requirements](docs/reference/requirements.md)
  - [Changelog](docs/reference/changelog.md)

## Prerequisites

- Python 3.8+
- Terraform >= 1.6
- kubectl
- Helm >= 3
- Cloud CLI (AWS CLI or Azure CLI)

See [requirements.md](docs/reference/requirements.md) for installation instructions.

## Project Structure

```
n8n-application/
├── setup.py              # Interactive deployment CLI
├── terraform/
│   ├── aws/             # AWS EKS infrastructure
│   └── azure/           # Azure AKS infrastructure
├── charts/n8n/          # Helm chart for n8n
├── docs/                # Documentation
└── setup_history.log    # Configuration history (auto-generated)
```

## Common Commands

```bash
# Deploy
python setup.py

# Deploy specific cloud
python setup.py --cloud-provider aws
python setup.py --cloud-provider azure

# Teardown
python setup.py --teardown

# Check deployment
kubectl get pods -n n8n
kubectl get svc -n ingress-nginx

# View configuration history
cat setup_history.log
```

## Configuration History

Every `setup.py` run automatically saves your configuration to `setup_history.log`. This helps you:
- Remember what parameters you used
- Retry after failures with same settings
- Track configuration changes over time

See [configuration-history.md](docs/guides/configuration-history.md) for details.

## Architecture

### AWS EKS
- VPC with public/private subnets across 3 AZs
- EKS cluster with managed node group
- RDS PostgreSQL or SQLite
- Network Load Balancer with Elastic IPs
- Secrets in AWS Parameter Store/Secrets Manager

### Azure AKS
- VNet with public/private subnets across 3 zones
- AKS cluster with managed node pool
- Azure Database for PostgreSQL or SQLite
- Azure Load Balancer with Public IP
- Secrets in Azure Key Vault

## Security

- Secrets stored in cloud key management services
- Network isolation with private subnets
- Kubernetes RBAC enabled
- Optional TLS/HTTPS with cert-manager
- Optional basic authentication

## Troubleshooting

### Azure Permission Errors

If you encounter authorization errors during Azure deployment, see:
- [Azure Permissions Guide](docs/guides/azure-permissions.md)
- `learnings/AZURE_MANUAL_PERMISSIONS.md`

### Deployment Failures

1. Check `setup_history.log` for your configuration
2. Infrastructure is preserved in Terraform state
3. Fix the issue and re-run `terraform apply` or `setup.py`

### Access Issues

```bash
# Get LoadBalancer IP/URL
kubectl get svc -n ingress-nginx

# Check pod status
kubectl get pods -n n8n

# View logs
kubectl logs -f deployment/n8n -n n8n
```

## Support

- **Issues:** GitHub Issues
- **Documentation:** See `docs/` directory
- **Configuration History:** `setup_history.log`

## License

[License Type]

## Contributing

Contributions welcome! Please read the contribution guidelines.
