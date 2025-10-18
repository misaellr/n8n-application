# N8N EKS Deployment - Changelog

## Version 1.7.0 (2025-10-17)

### New Features

#### 1. Multi-Region Terraform State Management
**Feature**: Added regionalization support for setup.py with automatic Terraform state backup and restore functionality.

**Implementation**:
- Region-specific state file management to prevent state conflicts across AWS regions
- Automatic state backup when deploying to a new region
- State restoration capability for switching between regional deployments
- Timestamp-based state snapshots for rollback capability

**Components**:
- `save_state_for_region()` - Saves current Terraform state with region-specific naming
- `restore_state_for_region()` - Restores Terraform state from region backup
- `list_available_state_backups()` - Lists all available state backups
- State validation to prevent overwriting non-empty states

**Files Modified**:
- `setup.py:946-1048` - Added state management functions
- State files: `terraform.tfstate.<region>.backup` format

**Usage**:
```python
# Automatically called during deployment
save_state_for_region(terraform_dir, region="us-west-1")
restore_state_for_region(terraform_dir, region="us-west-2")
```

**Benefits**:
- Safe multi-region deployments without state conflicts
- Ability to maintain separate n8n deployments in different AWS regions
- Protection against accidental state overwrites
- Easy region switching with state restoration

---

#### 2. Azure Kubernetes Service (AKS) Deployment Guide
**Feature**: Comprehensive documentation for deploying n8n on Azure Kubernetes Service.

**Implementation**:
- Complete Azure deployment guide (azure.md) with 1,000+ lines of documentation
- Mirrored architecture from AWS EKS deployment
- Azure-specific components: AKS, VNet, Key Vault, Azure Database for PostgreSQL
- Cost estimation for Azure infrastructure
- Troubleshooting and operational best practices

**Azure Components Documented**:
- **Compute**: AKS cluster with VMSS node pools
- **Networking**: VNet with public/private subnets, NAT Gateway, NSGs
- **Storage**: Azure Disk CSI driver with Premium SSD
- **Database**: Azure Database for PostgreSQL Flexible Server
- **Secrets**: Azure Key Vault for credentials management
- **Ingress**: NGINX controller with Azure Load Balancer

**Files Added**:
- `azure.md` - Complete Azure deployment guide

**Topics Covered**:
- Prerequisites and tool setup
- 4-phase deployment workflow
- Manual deployment steps
- Configuration reference
- Cost estimation (~$293-$493/month depending on configuration)
- Monitoring, backup, and high availability
- Security hardening and upgrade procedures
- Comprehensive troubleshooting guide

**Azure Services Mapped**:
- EKS → AKS
- VPC → Virtual Network (VNet)
- RDS → Azure Database for PostgreSQL
- SSM/Secrets Manager → Azure Key Vault
- IAM Roles → Managed Identities
- EBS → Azure Disk
- ELB/NLB → Azure Load Balancer

---

## Version 1.6.0 (2025-10-14)

### New Features

#### 1. TLS/SSL Certificate Configuration
**Feature**: Fully automated TLS/SSL certificate provisioning with Let's Encrypt integration.

**Implementation**:
- Integrated cert-manager for automated certificate management
- Let's Encrypt ClusterIssuer configuration for production certificates
- Automatic certificate issuance and renewal
- Certificate monitoring and validation commands

**Components**:
- Certificate Manager deployment with CRDs
- ClusterIssuer resource for Let's Encrypt production
- TLS ingress configuration with automatic certificate reference
- Certificate validity monitoring (3-month renewal cycle)

**Files Modified**:
- `helm/values.yaml:12-13` - Updated domain from n8n.example.com to n8n-aws.lrproducthub.com
- `helm/values.yaml:52-60` - Updated N8N_HOST, WEBHOOK_URL, and protocol configuration
- `setup.py` - TLS configuration workflow in Phase 4

**Verification Commands**:
```bash
kubectl get certificate -n n8n
kubectl describe certificate n8n-tls -n n8n
```

**Certificate Details**:
- Issuer: Let's Encrypt (R13)
- Validity: 90 days (auto-renewal at 30 days)
- Domain: n8n-aws.lrproducthub.com
- Protocol: TLS 1.2, TLS 1.3

---

#### 2. Infrastructure Teardown Functionality
**Feature**: Complete automated teardown of all deployment resources with `--teardown` flag.

**Implementation**: Added comprehensive TeardownRunner class with 4-phase destruction workflow:

**Phase 1: Helm Releases**
- Uninstall n8n application
- Remove ingress-nginx controller (waits for LoadBalancer deletion)
- Remove cert-manager (if exists)

**Phase 2: Kubernetes Resources**
- Delete PersistentVolumeClaims
- Clean up manual secrets (basic-auth, tls, db-credentials)
- Remove namespaces (n8n, ingress-nginx, cert-manager)

**Phase 3: Terraform Infrastructure**
- Detect and disable RDS deletion protection automatically
- Destroy EKS cluster, VPC, and all AWS resources
- Clean up security groups, IAM roles, and policies

**Phase 4: Secrets Manager Cleanup**
- Identify n8n-related secrets in AWS Secrets Manager
- Optional deletion with user confirmation
- Force delete without recovery period

**Safety Features**:
- Double confirmation required before proceeding
- 5-second countdown before execution
- Automatic detection of AWS region and profile from existing config
- Graceful handling of missing resources
- Comprehensive progress reporting

**Usage**:
```bash
python3 setup.py --teardown
```

**Files Modified**:
- `setup.py:1759-2158` - Added TeardownRunner class with complete teardown logic
- `setup.py:2221` - Added --teardown argument parser
- `setup.py:2239-2381` - Teardown execution flow with config detection

**Estimated Duration**: 10-20 minutes (depending on resource count)

---

#### 3. Multi-Region Support Enhancement
**Feature**: Improved support for AWS region selection with us-west-1 configuration.

**Changes**:
- Updated default region from us-east-1 to us-west-1
- Region-aware RDS and EKS deployment
- Automatic region detection for teardown operations

**Files Modified**:
- `terraform/variables.tf:9` - Updated default region to us-west-1

---

#### 4. Production Domain Configuration
**Feature**: Configured production domain for n8n deployment.

**Changes**:
- Domain: n8n-aws.lrproducthub.com
- HTTPS protocol with Let's Encrypt certificate
- Webhook URL configuration for external integrations
- CNAME record pointing to ELB in us-west-1

**Files Modified**:
- `helm/values.yaml:15` - ingress.host
- `helm/values.yaml:52` - N8N_HOST environment variable
- `helm/values.yaml:58` - WEBHOOK_URL configuration
- `terraform/variables.tf:94` - n8n_host default value

---

## Previous Changes (2025-10-14)

### Critical Fixes

#### 1. PostgreSQL Connection Failures (503 Service Unavailable) (FIXED)
**Issue**: After successful Helm deployment, n8n pods entered CrashLoopBackOff state with errors:
- Database connection timeout: "Could not establish database connection within 20,000 ms"
- SSL/TLS error: "no pg_hba.conf entry for host, no encryption"

**Root Causes**:
1. **Security Group Mismatch**: RDS security group only allowed connections from the custom `eks_nodes` security group, but EKS was assigning the cluster's default security group to worker nodes instead.
2. **Missing SSL Configuration**: n8n was attempting unencrypted connections to RDS PostgreSQL, which requires SSL by default on AWS.

**Solution**:

**A. Security Group Fix** (`terraform/main.tf:596-633`):
Updated RDS security group to accept connections from BOTH security groups:
```hcl
resource "aws_security_group" "rds" {
  # Allow connections from custom EKS nodes security group
  ingress {
    description     = "PostgreSQL from EKS worker nodes (custom SG)"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
  }

  # Allow connections from EKS cluster security group
  ingress {
    description     = "PostgreSQL from EKS cluster security group"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.main.vpc_config[0].cluster_security_group_id]
  }
}
```

**B. SSL Configuration Fix** (`setup.py:1143-1153`):
Added PostgreSQL SSL environment variables to Helm deployment:
```python
values_args.extend([
    '--set', 'database.type=postgresql',
    '--set', f'database.postgresql.host={db_config.get("rds_address", "")}',
    '--set', f'database.postgresql.port=5432',
    '--set', f'database.postgresql.database={db_config.get("rds_database_name", "n8n")}',
    '--set', f'database.postgresql.user={db_config.get("rds_username", "")}',
    # Enable SSL for RDS connections (required by AWS RDS)
    '--set', 'env.DB_POSTGRESDB_SSL_ENABLED=true',
    '--set', 'env.DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED=false',
])
```

**C. Deployment Template Update** (`helm/templates/deployment.yaml:66-69`):
Added default SSL environment variables to deployment template:
```yaml
- name: DB_POSTGRESDB_SSL_ENABLED
  value: "true"
- name: DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED
  value: "false"
```

**Files Modified**:
- `terraform/main.tf` - RDS security group dual-source configuration
- `setup.py` - Helm deployment with SSL environment variables
- `helm/templates/deployment.yaml` - Default PostgreSQL SSL configuration

**Impact**: Resolves 503 Service Unavailable errors and CrashLoopBackOff states when using PostgreSQL database

**Testing**: Verified by manually adding security group rule and SSL configuration, resulting in successful pod startup and healthy status

---

#### 2. Namespace Creation Race Condition (FIXED)
**Issue**: Deployment failed with error `namespaces "n8n" not found` when trying to create database credentials secret.

**Root Cause**: The setup.py script attempted to create Kubernetes secrets in the `n8n` namespace before the namespace was created. While Helm's `--create-namespace` flag was used, the secret creation happened in the Python code before the Helm command executed.

**Solution**: Modified `setup.py:1097-1118` to check if namespace exists and create it explicitly before creating secrets.

```python
# Ensure namespace exists before creating secret
namespace_check = subprocess.run(
    ['kubectl', 'get', 'namespace', namespace],
    capture_output=True
)
if namespace_check.returncode != 0:
    # Create namespace if it doesn't exist
    result = subprocess.run(
        ['kubectl', 'create', 'namespace', namespace],
        capture_output=True, text=True
    )
```

**Location**: `setup.py:1103-1118`

**Impact**: Resolved deployment failure in Phase 2 (n8n Application Deployment)

---

### Previous Fixes and Improvements

#### 2. Basic Authentication State Tracking
**Issue**: Basic auth state not properly tracked across deployments, leading to inconsistent cleanup and state management.

**Solution**:
- Added `enable_basic_auth` tracking in `terraform.tfvars`
- Updated configuration restore logic to preserve basic auth state
- Implemented proper cleanup of AWS Secrets Manager entries

**Files Modified**:
- `setup.py:1709-1728` - Added terraform.tfvars update for basic auth state
- `terraform/main.tf` - Added proper secret cleanup logic

---

#### 3. Cert-Manager Idempotency
**Issue**: Cert-manager would fail on redeployment if certificates already existed, causing Let's Encrypt configuration to fail.

**Solution**:
- Added idempotency checks for cert-manager installation
- Improved ClusterIssuer creation to handle existing resources
- Added proper certificate state verification

**Files Modified**:
- `setup.py:1441-1474` - Enhanced cert-manager installation logic
- Added checks for existing Helm releases before installation

**Commit**: `8bea82c - fix: resolve basic auth state tracking and cert-manager idempotency issues`

---

#### 4. Database Selection (PostgreSQL vs SQLite)
**Issue**: No option to choose between SQLite and PostgreSQL during initial setup.

**Solution**:
- Added interactive database selection during configuration
- Implemented RDS PostgreSQL provisioning via Terraform
- Added database credentials management via Kubernetes secrets
- Configured n8n Helm chart to support both database types

**Features Added**:
- Database type selection prompt
- RDS instance class configuration
- Storage allocation settings
- Multi-AZ deployment option
- Automatic password generation and secure storage

**Files Modified**:
- `setup.py:621-666` - Added database configuration prompts
- `setup.py:1097-1138` - Database-specific Helm deployment logic
- `terraform/main.tf` - RDS module integration
- `helm/values.yaml` - Database configuration support

**Commit**: `dbbd742 - feat: add database selection, basic auth, and fix critical deployment issues`

---

#### 5. 4-Phase Deployment Workflow
**Issue**: Let's Encrypt certificate requests failed due to DNS not being configured before cert-manager attempted validation.

**Solution**: Restructured deployment into 4 distinct phases:

**Phase 1: Infrastructure Deployment**
- VPC, subnets, NAT gateways
- EKS cluster and node groups
- NGINX ingress controller with LoadBalancer
- EBS CSI driver and StorageClass
- RDS PostgreSQL (if selected)

**Phase 2: N8N Application Deployment**
- Deploy n8n via Helm (HTTP only initially)
- Configure database connection
- Create necessary secrets

**Phase 3: LoadBalancer URL Retrieval**
- Wait for LoadBalancer to be provisioned
- Retrieve and display LoadBalancer DNS name
- Provide DNS configuration instructions

**Phase 4: TLS and Basic Auth Configuration**
- Interactive TLS configuration (Let's Encrypt or BYO cert)
- Interactive Basic Authentication setup
- Upgrade n8n deployment with security features

**Files Modified**:
- `setup.py:1787-1910` - Complete restructure of main() function
- Added phase separation with clear status indicators
- Improved user feedback and wait times

**Commit**: `b012624 - docs: update documentation for 4-phase deployment workflow`

---

#### 6. Robust Validation and Deployment Checks
**Issue**: Deployments would proceed even when critical resources weren't ready, leading to failures.

**Solution**:
- Added deployment readiness checks
- Implemented timeout handling for long-running operations
- Enhanced error reporting with actionable messages
- Added rollback capabilities

**Improvements**:
- Kubernetes deployment status verification
- LoadBalancer readiness polling with configurable timeouts
- Certificate validation before TLS configuration
- DNS configuration verification prompts

**Files Modified**:
- `setup.py:1204-1236` - Added `verify_n8n_deployment()` function
- `setup.py:1237-1277` - Enhanced `get_loadbalancer_url()` with retry logic
- Added comprehensive error handling throughout

**Commit**: `2585999 - feat: Implement robust validation and deployment checks`

---

## File Summary

### Modified Files

| File | Changes | Purpose |
|------|---------|---------|
| `setup.py` | Namespace creation fix, database support, 4-phase workflow | Main deployment script |
| `terraform/main.tf` | RDS module, secret cleanup, ingress configuration | Infrastructure as Code |
| `terraform/variables.tf` | Database variables, configuration options | Terraform variables |
| `helm/values.yaml` | Database configuration, ingress settings | Helm chart values |
| `.gitignore` | Added terraform state files | Exclude sensitive files |
| `REQUIREMENTS.md` | Updated dependencies and workflow | Documentation |

### New Files

| File | Purpose |
|------|---------|
| `terraform/nginx-ingress-values.tpl` | NGINX ingress controller configuration template |
| `terraform/terraform.tfvars` | User-specific Terraform configuration |
| `CHANGELOG.md` | This file - comprehensive change documentation |

---

## Known Issues Resolved

### ✅ Issue #1: Namespace Not Found
- **Error**: `error: failed to create secret namespaces "n8n" not found`
- **Status**: RESOLVED
- **Fix**: Pre-create namespace before secret creation

### ✅ Issue #2: Let's Encrypt Rate Limiting
- **Error**: Certificate requests failing due to LoadBalancer not ready
- **Status**: RESOLVED
- **Fix**: 4-phase deployment with explicit LoadBalancer wait

### ✅ Issue #3: Basic Auth Not Persisting
- **Error**: Basic auth configuration lost between deployments
- **Status**: RESOLVED
- **Fix**: Added state tracking in terraform.tfvars

### ✅ Issue #4: Database Connection Failures
- **Error**: N8N pod crashing when RDS credentials not available
- **Status**: RESOLVED
- **Fix**: Pre-create secrets in correct namespace before Helm deployment

---

## Deployment Time Estimates

| Phase | Duration | Components |
|-------|----------|------------|
| Phase 1: Infrastructure | 22-27 min | EKS, VPC, RDS, LoadBalancer |
| Phase 2: Application | 2-5 min | N8N Helm deployment |
| Phase 3: LoadBalancer | 1-5 min | DNS name retrieval |
| Phase 4: TLS & Auth | 3-10 min | Certificate issuance, configuration |
| **Total** | **28-47 min** | Complete deployment |

---

## Testing Recommendations

1. **Test Database Options**
   - Deploy with SQLite (default, simpler)
   - Deploy with PostgreSQL (production-grade)
   - Verify data persistence across pod restarts

2. **Test TLS Configuration**
   - Test with Let's Encrypt staging environment first
   - Verify DNS propagation before production certificates
   - Test BYO certificate option with valid certs

3. **Test Basic Authentication**
   - Verify credentials are properly stored in AWS Secrets Manager
   - Test access with and without credentials
   - Verify htpasswd bcrypt hashing

4. **Test Deployment Phases**
   - Test cancellation at each phase
   - Verify rollback functionality
   - Test redeployment scenarios

---

## Future Improvements

### Planned Enhancements

1. **Automated DNS Configuration**
   - Integration with Route53 for automatic DNS record creation
   - Support for other DNS providers (CloudFlare, etc.)

2. **Backup and Restore**
   - Automated backup of n8n workflows
   - RDS snapshot management
   - Disaster recovery procedures

3. **Monitoring and Alerting**
   - CloudWatch integration
   - Application-level monitoring
   - Cost tracking and optimization

4. **High Availability**
   - Multi-AZ EKS deployment
   - Auto-scaling configuration
   - Load balancing optimization

5. **CI/CD Integration**
   - GitHub Actions workflows
   - Automated testing pipeline
   - Blue-green deployments

---

## Dependencies

### Required Tools (Verified on Startup)

- **Python**: 3.7+ (Current: 3.8.10)
- **Terraform**: ≥1.6.0 (IaC for AWS resources)
- **AWS CLI**: ≥2.0.0 (AWS authentication and management)
- **Helm**: ≥3.0.0 (Kubernetes package management)
- **kubectl**: ≥1.20.0 (Kubernetes cluster management)
- **OpenSSL**: ≥1.1.1 (Certificate validation)
- **htpasswd**: Apache2-utils (Basic auth password hashing)

### Python Dependencies

- **boto3**: AWS SDK for Python (Secrets Manager integration)
- **botocore**: AWS SDK core functionality

### Optional Tools

- **jq**: JSON processing (helpful for debugging)
- **dig/nslookup**: DNS troubleshooting

---

## Configuration Files

### Persistent Configuration
- `terraform/terraform.tfvars` - User-specific Terraform variables
- `helm/values.yaml` - N8N Helm chart configuration
- AWS Secrets Manager: `/n8n/basic-auth` - Basic auth credentials

### Temporary Files (Git Ignored)
- `terraform/terraform.tfstate*` - Terraform state files
- `terraform/tfplan` - Terraform plan output
- `terraform/.terraform/` - Terraform plugins and modules

---

## Support and Troubleshooting

### Common Commands

```bash
# Check deployment status
kubectl get pods -n n8n
kubectl get ingress -n n8n
kubectl get svc -n ingress-nginx

# View logs
kubectl logs -f deployment/n8n -n n8n

# Check certificate status (if using Let's Encrypt)
kubectl get certificate -n n8n
kubectl describe certificate n8n-tls -n n8n

# Verify database connectivity
kubectl exec -it deployment/n8n -n n8n -- /bin/sh
# Inside pod: check environment variables for DB config
```

### Re-running Configuration

```bash
# Configure TLS for existing deployment
python3 setup.py --configure-tls

# Full redeployment
python3 setup.py
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.7.0 | 2025-10-17 | Multi-region state management, Azure AKS deployment guide |
| 1.6.0 | 2025-10-14 | TLS/SSL cert automation, teardown functionality, multi-region support |
| 1.5.0 | 2025-10-14 | Fixed PostgreSQL connection failures (security groups + SSL) |
| 1.4.0 | 2025-10-14 | Fixed namespace creation race condition |
| 1.3.0 | 2025-10-14 | Added basic auth state tracking, cert-manager idempotency |
| 1.2.0 | 2025-10-13 | Implemented 4-phase deployment workflow |
| 1.1.0 | 2025-10-13 | Added database selection (PostgreSQL/SQLite) |
| 1.0.0 | 2025-10-12 | Initial release with EKS deployment |

---

## Contributors

- Development and testing on AWS EKS
- Terraform infrastructure management
- Python automation scripting
- Kubernetes resource orchestration

---

## License

This deployment automation is provided as-is for N8N self-hosted deployments on AWS EKS.

---

*Last Updated: October 17, 2025*
