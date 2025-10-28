# GCP Terraform Module for n8n Deployment

This Terraform module deploys a production-ready n8n instance on Google Cloud Platform (GCP) using Google Kubernetes Engine (GKE).

## Architecture Overview

The module creates the following GCP resources:

- **GKE Cluster**: Regional Kubernetes cluster with workload identity
- **VPC Network**: Custom VPC with private subnets and secondary IP ranges for pods/services
- **Cloud NAT**: Outbound internet access for private nodes
- **Service Accounts**: Three service accounts with least-privilege IAM roles
  - GKE Cluster SA (cluster operations)
  - GKE Nodes SA (logging, monitoring, artifact registry)
  - N8N Workload SA (Secret Manager, Cloud SQL access)
- **Secret Manager**: Encrypted storage for n8n encryption keys and credentials
- **Cloud SQL PostgreSQL** (optional): Managed database with private IP connectivity

## Prerequisites

1. **GCP Account**: Active GCP account with billing enabled
2. **GCP Project**: Create or select a GCP project
3. **Required APIs**: Enable the following APIs in your project:
   ```bash
   gcloud services enable compute.googleapis.com
   gcloud services enable container.googleapis.com
   gcloud services enable servicenetworking.googleapis.com
   gcloud services enable secretmanager.googleapis.com
   gcloud services enable sqladmin.googleapis.com  # Only if using Cloud SQL
   ```

4. **IAM Permissions**: Your user/service account needs these roles:
   - `roles/compute.admin` (Compute Engine management)
   - `roles/container.admin` (GKE management)
   - `roles/iam.serviceAccountAdmin` (Service account creation)
   - `roles/iam.securityAdmin` (IAM policy binding)
   - `roles/secretmanager.admin` (Secret Manager management)
   - `roles/cloudsql.admin` (Cloud SQL management - if using Cloud SQL)
   - `roles/servicenetworking.networksAdmin` (VPC peering - if using Cloud SQL)

5. **Tools**:
   - Terraform >= 1.6.0 ([install](https://www.terraform.io/downloads))
   - gcloud CLI ([install](https://cloud.google.com/sdk/docs/install))
   - kubectl ([install](https://kubernetes.io/docs/tasks/tools/))

## Quick Start

### 1. Authenticate with GCP

```bash
# Login to GCP
gcloud auth login

# Set your default project
gcloud config set project YOUR_PROJECT_ID

# Configure application default credentials for Terraform
gcloud auth application-default login
```

### 2. Prepare Configuration

```bash
# Navigate to terraform directory
cd terraform/gcp

# Copy example configuration
cp terraform.tfvars.example terraform.tfvars

# Generate encryption key
openssl rand -hex 32

# Edit terraform.tfvars with your values
# At minimum, set: gcp_project_id, gcp_region, n8n_encryption_key
vim terraform.tfvars
```

### 3. Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Review the deployment plan
terraform plan

# Apply the configuration
terraform apply
```

Deployment typically takes 10-15 minutes.

### 4. Configure kubectl

```bash
# Get kubectl configuration command from outputs
terraform output kubectl_config_command

# Or run directly:
gcloud container clusters get-credentials $(terraform output -raw cluster_name) \
  --region $(terraform output -raw region) \
  --project $(terraform output -raw project_id)

# Verify connectivity
kubectl get nodes
```

## Configuration Options

### Database Options

#### SQLite (Default)
- Embedded database running in pod
- Lower cost (~$168/month for 2 nodes)
- Suitable for development and small workloads
- Simpler setup, no external database

```hcl
database_type = "sqlite"
```

#### Cloud SQL PostgreSQL
- Managed PostgreSQL database
- Higher cost (~$324/month with db-n1-standard-1)
- Production-ready with automated backups
- Point-in-time recovery
- Optional high availability (REGIONAL)

```hcl
database_type = "cloudsql"
cloudsql_tier = "db-n1-standard-1"
cloudsql_availability_type = "ZONAL"  # or "REGIONAL" for HA
cloudsql_username = "n8n"
cloudsql_password = "secure-password-here"
```

### Node Configuration

**Development/Testing:**
```hcl
node_count = 1
node_machine_type = "e2-small"  # 2 vCPU, 2GB RAM
```

**Production (Small):**
```hcl
node_count = 2
node_machine_type = "e2-medium"  # 2 vCPU, 4GB RAM
```

**Production (Standard):**
```hcl
node_count = 3
node_machine_type = "n2-standard-2"  # 2 vCPU, 8GB RAM
```

### Security Options

#### Basic Authentication
```hcl
enable_basic_auth = true
basic_auth_username = "admin"
basic_auth_password = "secure-password"
```

## Outputs

After deployment, access important information via outputs:

```bash
# View all outputs
terraform output

# Specific outputs
terraform output cluster_name
terraform output cluster_endpoint
terraform output n8n_workload_sa_email
terraform output cloudsql_instance_connection_name  # if using Cloud SQL
```

## Post-Deployment

After Terraform completes, proceed with Kubernetes deployment:

1. **Configure kubectl** (see step 4 above)
2. **Deploy n8n using Helm** (automated via `setup.py`)
3. **Configure DNS and ingress** (see main README)

## Workload Identity Setup

The module configures workload identity for secure GCP service access. The Kubernetes service account must be annotated:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: n8n
  namespace: n8n
  annotations:
    iam.gke.io/gcp-service-account: <WORKLOAD_SA_EMAIL>
```

Get the annotation value:
```bash
terraform output workload_identity_annotation
```

## Cost Optimization

### Development/Testing
- Use `database_type = "sqlite"`
- Minimum node count: `node_count = 1`
- Smaller machine type: `node_machine_type = "e2-small"`
- Estimated: ~$120-170/month

### Production Cost Reduction
- Use preemptible nodes (not configured in this module)
- Enable GKE cluster autoscaling
- Use committed use discounts
- Right-size node machine types based on actual usage
- Consider Cloud SQL ZONAL vs REGIONAL (2x cost difference)

## Troubleshooting

### Terraform Validation Errors

**Error: "value is marked, so must be unmarked first"**
- Ensure `n8n_encryption_key` is provided in `terraform.tfvars`
- Do not use empty string for sensitive variables

**Error: "Duplicate variable declaration"**
- Check for conflicting variable definitions
- Ensure no duplicate variable blocks

### GKE Cluster Access

**Cannot connect to cluster:**
```bash
# Re-authenticate
gcloud auth login
gcloud auth application-default login

# Update kubectl config
gcloud container clusters get-credentials CLUSTER_NAME --region REGION --project PROJECT_ID

# Verify
kubectl cluster-info
```

### Cloud SQL Connection Issues

**Private IP not accessible:**
- Verify VPC peering is established
- Check firewall rules allow GKE to Cloud SQL traffic
- Ensure Cloud SQL instance has private IP enabled

### API Not Enabled

```bash
# List enabled APIs
gcloud services list --enabled

# Enable missing APIs
gcloud services enable compute.googleapis.com container.googleapis.com
```

## Cleanup

To destroy all resources:

```bash
# Review what will be destroyed
terraform plan -destroy

# Destroy all resources
terraform destroy
```

**Warning**: This will permanently delete:
- GKE cluster and all running workloads
- Cloud SQL database and all data (if using Cloud SQL)
- VPC network and subnets
- Service accounts
- Secret Manager secrets

## Security Best Practices

1. **Never commit `terraform.tfvars`** - Contains secrets
2. **Use Secret Manager** - Don't hardcode secrets in manifests
3. **Enable deletion protection** in production:
   ```hcl
   # In cloudsql.tf and secrets.tf
   deletion_protection = true
   prevent_destroy = true
   ```
4. **Restrict master authorized networks** - Limit kubectl access
5. **Review IAM permissions** - Follow least-privilege principle
6. **Enable Cloud Audit Logging** - Track API calls
7. **Rotate encryption keys** - Periodically update secrets

## Module Files

- `versions.tf` - Terraform and provider version constraints
- `variables.tf` - Input variable definitions with validations
- `main.tf` - Provider configuration and common locals
- `vpc.tf` - VPC network, subnets, Cloud Router, Cloud NAT
- `iam.tf` - Service accounts and IAM role bindings
- `gke.tf` - GKE cluster and node pool configuration
- `secrets.tf` - Secret Manager resources
- `cloudsql.tf` - Cloud SQL PostgreSQL (conditional)
- `outputs.tf` - Output values for automation
- `.gitignore` - Prevents committing sensitive files

## Additional Resources

- [GCP GKE Documentation](https://cloud.google.com/kubernetes-engine/docs)
- [Workload Identity Guide](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Cloud SQL for PostgreSQL](https://cloud.google.com/sql/docs/postgres)
- [GCP Pricing Calculator](https://cloud.google.com/products/calculator)
- [n8n Documentation](https://docs.n8n.io/)

## Support

For issues related to:
- **This Terraform module**: Open an issue in this repository
- **GCP platform**: [GCP Support](https://cloud.google.com/support)
- **n8n application**: [n8n Community](https://community.n8n.io/)
