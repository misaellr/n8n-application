# AWS EKS Deployment

Quick guide to deploy n8n on Amazon EKS using the automated setup CLI.

## What Gets Deployed

- **Infrastructure**: VPC, EKS cluster, managed node group, NAT gateway
- **Networking**: Network Load Balancer with AWS-managed Elastic IPs
- **Storage**: EBS CSI driver with gp3 volumes
- **Database**: SQLite (default) or PostgreSQL (RDS)
- **Secrets**: AWS Systems Manager Parameter Store & Secrets Manager
- **TLS**: Optional cert-manager with Let's Encrypt

## Prerequisites

```bash
# Required tools
python3 --version  # >= 3.8
terraform --version  # >= 1.6
kubectl version --client
helm version
aws --version  # >= 2.0

# AWS credentials
aws configure --profile <your-profile>
aws sts get-caller-identity --profile <your-profile>
```

See [Requirements](../reference/requirements.md) for installation instructions.

## Deploy

```bash
# Run interactive setup
python3 setup.py

# Follow prompts:
# 1. Cloud provider: aws
# 2. AWS profile & region
# 3. Cluster configuration (or use defaults)
# 4. Database: SQLite or PostgreSQL
# 5. Confirm and deploy
```

**Deployment time**: ~25 minutes

## What Happens

### Phase 1: Infrastructure (~20 min)
- Terraform creates VPC, EKS cluster, node group
- Installs ingress-nginx controller (NLB)
- Stores encryption key in Parameter Store

### Phase 2: Application (~2 min)
- Deploys n8n via Helm
- Configures database connection
- Sets up ingress routing

### Phase 3: Access (~1 min)
- Retrieves LoadBalancer URL
- Displays access information

### Phase 4: TLS (Optional, ~5 min)
- Configure DNS
- Install cert-manager
- Issue Let's Encrypt certificate

## Access Your Deployment

```bash
# Get LoadBalancer URL
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

# Check n8n status
kubectl get pods -n n8n
kubectl logs -f deployment/n8n -n n8n
```

## Configure DNS

```bash
# Get NLB hostname
NLB_HOSTNAME=$(kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Option 1: CNAME (recommended)
# Create CNAME: n8n.yourdomain.com -> $NLB_HOSTNAME

# Option 2: A record
# Get IP: dig +short $NLB_HOSTNAME
# Create A record: n8n.yourdomain.com -> <IP>
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
| NAT Gateway EIP | Terraform | 1 EIP for cost efficiency |
| NLB EIPs | AWS-managed | Auto-allocated across AZs |
| VPC, EKS, RDS | Terraform | In terraform state |

**Important**: NLB IPs may change if recreated. Use CNAME for DNS when possible.

## Cost Estimate

**Default Configuration (us-east-1, SQLite)**:
- EKS Control Plane: $73/month
- t3.medium node: $30/month
- NAT Gateway: $33/month
- NLB: $16/month
- **Total: ~$157/month**

**With PostgreSQL**: Add $15-60/month for RDS

## Configuration Options

Edit `terraform.tfvars` or use CLI prompts:

```hcl
# Cluster
cluster_name = "n8n-eks-cluster"
node_instance_types = ["t3.medium"]
node_desired_size = 1

# Database
database_type = "sqlite"  # or "postgresql"

# Networking
enable_nginx_ingress = true
vpc_cidr = "10.0.0.0/16"

# n8n
n8n_host = "n8n.yourdomain.com"
n8n_protocol = "https"
```

## Troubleshooting

### Permission Errors
```bash
# Verify IAM permissions
aws sts get-caller-identity --profile <profile>
aws iam get-user --profile <profile>
```

### Deployment Failures
```bash
# Check Terraform state
cd terraform/aws
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
cd terraform/aws
terraform destroy
```

## Next Steps

- [Enable Basic Auth](../guides/configuration-history.md)
- [Configure Backups](#)
- [Set up Monitoring](#)
- [Scale Cluster](#)

## Support

- [Requirements](../reference/requirements.md)
- [Configuration History](../guides/configuration-history.md)
- GitHub Issues
