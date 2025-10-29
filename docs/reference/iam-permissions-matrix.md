# IAM Permissions Matrix - Multi-Cloud Comparison

Comprehensive cross-cloud IAM/RBAC permissions required for n8n deployment across AWS, Azure, and GCP.

## Quick Reference

| Cloud | Minimum Role Set | Cost Impact | Complexity |
|-------|------------------|-------------|------------|
| **AWS** | 10-12 service permissions | None | Medium |
| **Azure** | 2-4 role assignments | None | Low |
| **GCP** | 5-7 predefined roles | None | Medium |

---

## Philosophy: Least Privilege Approach

This guide follows the **principle of least privilege**: grant only the minimum permissions required for deployment and teardown operations.

### Key Principles

1. **No Owner/Administrator roles** - Avoid overly broad permissions
2. **Scope to resource groups/projects** - Never grant organization-wide access
3. **Separate deployment from runtime** - Deployment credentials ≠ application credentials
4. **Terraform-managed resources** - All IAM for runtime workloads created by Terraform

---

## AWS IAM Permissions

### Overview

AWS uses **IAM policies** attached to users or roles. Permissions are action-based.

### Minimum Required Permissions

#### Core Infrastructure (Required)

| Service | Actions | Reason |
|---------|---------|--------|
| **EC2** | `ec2:*` | VPC, subnets, security groups, NAT gateways, Elastic IPs, route tables |
| **EKS** | `eks:*` | Kubernetes cluster creation, node groups, OIDC provider |
| **IAM** | `iam:*` | Service roles for EKS, node groups, load balancer controller |
| **ELB** | `elasticloadbalancing:*` | Network Load Balancer for ingress controller |

#### Storage & Secrets (Required)

| Service | Actions | Reason |
|---------|---------|--------|
| **SSM** | `ssm:PutParameter`, `ssm:GetParameter`, `ssm:DeleteParameter` | Store n8n encryption key |
| **Secrets Manager** | `secretsmanager:*` | Alternative to SSM for encryption key |

#### Database (Optional - PostgreSQL only)

| Service | Actions | Reason |
|---------|---------|--------|
| **RDS** | `rds:*` | PostgreSQL database creation, deletion |

### IAM Policy Template

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CoreInfrastructure",
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "eks:*",
        "iam:*",
        "elasticloadbalancing:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsManagement",
      "Effect": "Allow",
      "Action": [
        "ssm:PutParameter",
        "ssm:GetParameter",
        "ssm:DeleteParameter",
        "ssm:DescribeParameters",
        "ssm:AddTagsToResource",
        "secretsmanager:CreateSecret",
        "secretsmanager:GetSecretValue",
        "secretsmanager:DeleteSecret",
        "secretsmanager:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DatabaseOptional",
      "Effect": "Allow",
      "Action": [
        "rds:CreateDBInstance",
        "rds:DeleteDBInstance",
        "rds:DescribeDBInstances",
        "rds:CreateDBSubnetGroup",
        "rds:DeleteDBSubnetGroup",
        "rds:ModifyDBInstance",
        "rds:AddTagsToResource"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "us-west-1"
        }
      }
    }
  ]
}
```

### Quick Setup

```bash
# Option 1: Use AdministratorAccess (simplest, not recommended for production)
aws sts get-caller-identity --profile <profile>

# Option 2: Attach custom policy to IAM user
aws iam put-user-policy \
  --user-name <username> \
  --policy-name N8NDeploymentPolicy \
  --policy-document file://n8n-deployment-policy.json
```

### References
- [AWS IAM Permissions Guide](../guides/aws-permissions.md)
- [AWS Policy Simulator](https://policysim.aws.amazon.com/)

---

## Azure RBAC Permissions

### Overview

Azure uses **Role-Based Access Control (RBAC)** with built-in and custom roles. Permissions are role-based, scoped to resource groups.

### Minimum Required Roles

#### For Terraform Deployment User/Service Principal

| Role | Scope | Reason |
|------|-------|--------|
| **Contributor** | Resource Group | Create/modify all resources (VNet, AKS, Key Vault, PostgreSQL) |
| **User Access Administrator** (optional) | Resource Group | Assign roles to managed identities (if `terraform_manage_role_assignments = true`) |

#### For AKS Cluster Managed Identity (Created by Terraform)

| Role | Scope | Reason |
|------|-------|--------|
| **Network Contributor** | Resource Group | Allow AKS to create LoadBalancer, attach to subnets |
| **Key Vault Secrets User** | Key Vault | Read n8n encryption key from Key Vault |

### Role Assignment Matrix

| Principal | Role | Scope | Who Assigns | When |
|-----------|------|-------|-------------|------|
| **Deployment User** | Contributor | Resource Group | Azure Admin | Before deployment |
| **Deployment User** | User Access Administrator | Resource Group | Azure Admin | Before deployment (if Terraform manages roles) |
| **AKS Managed Identity** | Network Contributor | Resource Group | Terraform or Azure Admin | During/after deployment |
| **AKS Managed Identity** | Key Vault Secrets User | Key Vault | Terraform or Azure Admin | During/after deployment |

### Quick Setup

#### Option 1: Terraform Manages Roles (Recommended)

```bash
# Set this in terraform.tfvars
terraform_manage_role_assignments = true

# Your user needs:
# - Contributor on resource group
# - User Access Administrator on resource group
```

#### Option 2: Manual Role Assignment

```bash
# Get AKS managed identity principal ID after deployment
AKS_IDENTITY=$(az aks show --resource-group n8n-rg --name n8n-aks-cluster \
  --query 'identity.principalId' -o tsv)

# Assign Network Contributor
az role assignment create \
  --assignee $AKS_IDENTITY \
  --role "Network Contributor" \
  --resource-group n8n-rg

# Assign Key Vault Secrets User
KEYVAULT_ID=$(az keyvault show --name <vault-name> --query id -o tsv)
az role assignment create \
  --assignee $AKS_IDENTITY \
  --role "Key Vault Secrets User" \
  --scope $KEYVAULT_ID
```

### Common Issues

❌ **LoadBalancer stuck in `<pending>` state**
- **Cause:** AKS managed identity missing `Network Contributor` role
- **Fix:** Assign role manually (see above)

❌ **Pod can't read Key Vault secrets**
- **Cause:** AKS managed identity missing `Key Vault Secrets User` role
- **Fix:** Assign role and restart pod

### References
- [Azure Permissions Guide](../guides/azure-permissions.md)
- [Azure Built-in Roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles)

---

## GCP IAM Permissions

### Overview

GCP uses **IAM roles** (predefined and custom) attached to users or service accounts. Permissions are action-based but grouped into roles.

### Minimum Required Roles

#### Core Infrastructure (Required)

| Role | Permissions | Reason |
|------|-------------|--------|
| **roles/compute.networkAdmin** | VPC, subnets, Cloud NAT, firewall rules, external IPs | Full network management |
| **roles/container.clusterAdmin** | GKE cluster and node pool operations | Kubernetes cluster management |
| **roles/iam.serviceAccountAdmin** | Create/delete service accounts | For workload identity service accounts |
| **roles/iam.serviceAccountUser** | Use service accounts | Attach service accounts to GKE nodes |
| **roles/secretmanager.admin** | Create, read, delete secrets | Store n8n encryption key |

#### Database (Optional - PostgreSQL only)

| Role | Permissions | Reason |
|------|-------------|--------|
| **roles/cloudsql.admin** | Cloud SQL instance creation, deletion | PostgreSQL database |

### Role Assignment Matrix

| Principal | Role | When Needed | Scope |
|-----------|------|-------------|-------|
| **Deployment User** | compute.networkAdmin | Always | Project |
| **Deployment User** | container.clusterAdmin | Always | Project |
| **Deployment User** | iam.serviceAccountAdmin | Always | Project |
| **Deployment User** | secretmanager.admin | Always | Project |
| **Deployment User** | cloudsql.admin | PostgreSQL only | Project |
| **GKE Node Service Account** | (created by Terraform) | Runtime | Project |
| **Workload Identity SA** | secretmanager.secretAccessor | Runtime | Project |

### Quick Setup

#### For User Account

```bash
# Get current user
USER_EMAIL=$(gcloud config get-value account)
PROJECT_ID=$(gcloud config get-value project)

# Assign core roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/compute.networkAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/container.clusterAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/iam.serviceAccountAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/secretmanager.admin"

# For PostgreSQL deployments
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/cloudsql.admin"
```

#### For Service Account (CI/CD)

```bash
# Create service account
gcloud iam service-accounts create n8n-deployer \
  --display-name="N8N Deployment Service Account"

SA_EMAIL=n8n-deployer@$PROJECT_ID.iam.gserviceaccount.com

# Assign roles
for role in compute.networkAdmin container.clusterAdmin iam.serviceAccountAdmin iam.serviceAccountUser secretmanager.admin; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/$role"
done

# Generate key
gcloud iam service-accounts keys create ~/n8n-deployer-key.json \
  --iam-account=$SA_EMAIL
```

### Roles to AVOID

❌ **Too Broad:**
- `roles/owner` - Full project access
- `roles/editor` - Can modify everything
- `roles/resourcemanager.projectIamAdmin` - Can grant any IAM permission

### References
- [GCP Requirements Guide](../guides/gcp-requirements.md)
- [GCP Predefined Roles](https://cloud.google.com/iam/docs/understanding-roles)

---

## Cross-Cloud Comparison

### Permission Scope Comparison

| Aspect | AWS | Azure | GCP |
|--------|-----|-------|-----|
| **Granularity** | Action-level (fine) | Role-level (coarse) | Role-level (medium) |
| **Scope Options** | Resource ARNs, tags, conditions | Resource group, subscription, resource | Project, folder, organization |
| **Role Count** | 1 custom policy | 2-4 built-in roles | 5-7 predefined roles |
| **Ease of Setup** | Medium (write JSON) | Easy (assign roles) | Medium (multiple role commands) |
| **Least Privilege** | High (fine-grained) | Medium (coarse roles) | Medium (grouped permissions) |

### Deployment User Permissions

| Cloud | What's Needed | Why |
|-------|---------------|-----|
| **AWS** | IAM policy with 10-12 service actions | Create infrastructure, no separate role assignments needed |
| **Azure** | Contributor + (optionally) User Access Admin | Create resources + assign roles to managed identity |
| **GCP** | 5-7 predefined roles | Create infrastructure + service accounts |

### Runtime Workload Permissions

| Cloud | How Managed | Identity Type |
|-------|-------------|---------------|
| **AWS** | IRSA (IAM Roles for Service Accounts) | IAM Role with OIDC trust |
| **Azure** | Workload Identity (Azure AD Pod Identity successor) | Managed Identity |
| **GCP** | Workload Identity | Service Account with IAM binding |

**Key Difference:** All three use similar OIDC-based patterns, but Azure requires explicit role assignments to the AKS managed identity.

---

## Troubleshooting Permission Issues

### AWS

**Symptoms:**
- Terraform errors mentioning "UnauthorizedOperation"
- EKS cluster creation fails
- LoadBalancer won't provision

**Diagnosis:**
```bash
# Verify identity
aws sts get-caller-identity --profile <profile>

# Test IAM policy simulator (AWS Console)
# https://policysim.aws.amazon.com/
```

**Common Fixes:**
1. Attach missing IAM policy actions
2. Remove resource-level restrictions (use `"Resource": "*"` for simplicity)
3. Check AWS region matches deployment region

### Azure

**Symptoms:**
- "LinkedAuthorizationFailed" in Azure Portal
- LoadBalancer stuck in `<pending>`
- Pod logs show "403 Forbidden" from Key Vault

**Diagnosis:**
```bash
# Check role assignments
az role assignment list --resource-group n8n-rg --output table

# Get AKS managed identity
az aks show --resource-group n8n-rg --name n8n-aks-cluster \
  --query 'identity.principalId' -o tsv
```

**Common Fixes:**
1. Assign `Network Contributor` to AKS managed identity
2. Assign `Key Vault Secrets User` to AKS managed identity
3. Set `terraform_manage_role_assignments = true` in terraform.tfvars

### GCP

**Symptoms:**
- "403 Forbidden" or "Permission denied" from gcloud/Terraform
- GKE cluster creation fails
- Secret Manager access errors

**Diagnosis:**
```bash
# Verify identity
gcloud config get-value account
gcloud projects get-iam-policy $(gcloud config get-value project) \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:$(gcloud config get-value account)"
```

**Common Fixes:**
1. Assign missing predefined roles
2. Enable required APIs (compute, container, secretmanager, sqladmin)
3. Wait 60 seconds for IAM propagation after role assignment

---

## Security Best Practices

### 1. Use Service Accounts for CI/CD

**Don't:** Use personal user credentials in automation

**Do:** Create dedicated service accounts/service principals with minimal permissions

### 2. Scope Permissions Narrowly

**Don't:** Grant Owner/Administrator roles

**Do:** Use least privilege roles scoped to resource groups/projects

### 3. Rotate Credentials Regularly

**AWS:** Rotate access keys every 90 days
**Azure:** Use Managed Identities (no credential rotation needed)
**GCP:** Rotate service account keys every 90 days

### 4. Audit IAM Changes

**AWS:** Enable CloudTrail
**Azure:** Enable Activity Log
**GCP:** Enable Cloud Audit Logs

### 5. Separate Deployment from Runtime

**Deployment credentials:** Broad permissions for infrastructure creation
**Runtime credentials:** Narrow permissions for application operations only

---

## Cost Impact

**All IAM/RBAC permissions are free.**

There is **zero cost** for:
- Creating IAM users, roles, policies (AWS)
- Assigning Azure RBAC roles
- Creating GCP service accounts and assigning IAM roles

The only costs are for the actual resources created (VMs, storage, databases, etc.).

---

## Quick Reference Commands

### AWS

```bash
# Verify identity
aws sts get-caller-identity --profile <profile>

# List IAM policies
aws iam list-attached-user-policies --user-name <username>

# Test permissions
aws eks describe-cluster --name <cluster> --region <region>
```

### Azure

```bash
# Verify identity
az account show

# List role assignments
az role assignment list --assignee <object-id> --output table

# Test permissions
az aks show --resource-group <rg> --name <cluster>
```

### GCP

```bash
# Verify identity
gcloud config get-value account

# List IAM roles
gcloud projects get-iam-policy $(gcloud config get-value project) \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:$(gcloud config get-value account)"

# Test permissions
gcloud container clusters describe <cluster> --region <region>
```

---

## Related Documentation

- [AWS IAM Permissions Guide](../guides/aws-permissions.md) - Detailed AWS setup
- [Azure Permissions Guide](../guides/azure-permissions.md) - Detailed Azure RBAC setup
- [GCP Requirements Guide](../guides/gcp-requirements.md) - Detailed GCP IAM setup
- [Requirements Overview](requirements.md) - General prerequisites

---

*Last Updated: October 28, 2025*
*Validated against: AWS EKS, Azure AKS, GCP GKE deployments*
