# Azure AKS Deployment Challenges & Learnings

This document captures the challenges encountered and lessons learned while implementing Azure AKS infrastructure with Terraform and Helm for n8n deployment.

## Environment

- **Cloud Provider**: Microsoft Azure
- **Region**: East US (`eastus`)
- **Kubernetes**: AKS (Azure Kubernetes Service)
- **IaC Tool**: Terraform v3.117.1 (AzureRM provider)
- **Package Manager**: Helm v3
- **Date**: October 2025

---

## Challenge 1: NAT Gateway Zone Configuration

### Problem
```
Error: creating Nat Gateway: unexpected status 400 (400 Bad Request)
Message: Resource has 3 zones specified. Only one zone can be specified for this resource.
```

**Code that failed:**
```terraform
resource "azurerm_nat_gateway" "main" {
  name                = "${local.project_tag}-nat-gateway"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = "Standard"
  zones               = ["1", "2", "3"]  # ❌ This doesn't work!
}
```

### Root Cause
Azure NAT Gateway has different zone behavior than AWS NAT Gateway:
- **AWS**: Can specify multiple availability zones for high availability
- **Azure**: Supports either:
  - **Zone-redundant** (no zones parameter) - automatically distributes across zones
  - **Zonal** (single zone) - pinned to one specific zone

### Solution
Remove the `zones` parameter entirely to make it zone-redundant:

```terraform
resource "azurerm_nat_gateway" "main" {
  name                = "${local.project_tag}-nat-gateway"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = "Standard"
  # ✅ Omit zones parameter for zone-redundant deployment
}
```

**Also affected:**
- `azurerm_public_ip.nat` - NAT Gateway Public IP
- `azurerm_public_ip.lb` - Load Balancer Public IP

### Lessons Learned
1. **Azure zones != AWS zones**: Different cloud providers have different high availability models
2. **Zone-redundant is better**: Omitting zones provides better cross-region compatibility
3. **Check region support**: Not all Azure regions support all availability zones equally
   - `eastus` only supports zone `2` in some services
   - `westus2`, `centralus` have full 1,2,3 zone support

---

## Challenge 2: AKS Availability Zones

### Problem
```
Error: creating Kubernetes Cluster: unexpected status 400 (400 Bad Request)
Message: The zone(s) '3' for resource 'system' is not supported.
The supported zones for location 'eastus' are '2'
```

**Code that failed:**
```terraform
default_node_pool {
  name    = "system"
  vm_size = var.node_vm_size
  zones   = ["1", "2", "3"]  # ❌ eastus doesn't support zones 1 and 3
}
```

### Root Cause
- Azure regions have **inconsistent zone support** across services
- `eastus` region had limited zone support for AKS node pools at deployment time
- Zone availability varies by:
  - Azure region
  - VM SKU/size
  - Service type

### Solution
Remove explicit zone assignment and let Azure handle distribution:

```terraform
default_node_pool {
  name    = "system"
  vm_size = var.node_vm_size
  # ✅ Let Azure handle zone distribution automatically
  enable_auto_scaling = var.enable_auto_scaling
  node_count          = var.enable_auto_scaling ? null : var.node_count
}
```

### Lessons Learned
1. **Check zone availability per region**: Use `az aks get-versions --location <region>` to verify
2. **Design for portability**: Omitting zones makes configs work across regions
3. **Azure docs can lag**: Real-time Azure limitations may not be fully documented

---

## Challenge 3: Kubernetes Version LTS Requirements

### Problem
```
Error: creating Kubernetes Cluster: unexpected status 400 (400 Bad Request)
Message: Managed cluster is on version 1.29.15, which is only available for Long-Term Support (LTS).
If you intend to onboard to LTS, please ensure the cluster is in Premium tier and LTS support plan.
```

**Configuration that failed:**
```terraform
variable "kubernetes_version" {
  default = "1.29"
}
```

### Root Cause
- Kubernetes `1.29.x` moved to **LTS-only** support in Azure
- LTS requires:
  - **Premium tier** AKS cluster (higher cost)
  - Explicit **LTS support plan** opt-in
- Standard tier only supports newer versions

### Solution
Upgrade to a newer, actively-supported version:

```bash
# Check available versions
az aks get-versions --location eastus --output table

# Use a KubernetesOfficial version
variable "kubernetes_version" {
  default = "1.31.11"  # ✅ Supports both KubernetesOfficial and LTS
}
```

**Output from version check:**
```
KubernetesVersion    SupportPlan
-------------------  --------------------------------------
1.33.3               KubernetesOfficial, AKSLongTermSupport
1.32.7               KubernetesOfficial, AKSLongTermSupport
1.31.11              KubernetesOfficial, AKSLongTermSupport  ✅
1.30.14              AKSLongTermSupport
1.29.15              AKSLongTermSupport                      ❌
```

### Lessons Learned
1. **Check version support plans**: Not all versions support standard tier
2. **Use `KubernetesOfficial` versions**: They work on both Standard and Premium tiers
3. **Stay relatively current**: Older versions have more restrictions
4. **Version changes frequently**: Always verify with `az aks get-versions`

---

## Challenge 4: Role Assignment Permissions

### Problem
```
Error: authorization.RoleAssignmentsClient#Create: StatusCode=403
Message: The client 'user@company.com' does not have authorization to perform action
'Microsoft.Authorization/roleAssignments/write' over scope
```

**Code that failed:**
```terraform
resource "azurerm_role_assignment" "aks_network_contributor" {
  scope                = azurerm_virtual_network.main.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
}
```

### Root Cause
- Creating role assignments requires **User Access Administrator** or **Owner** role
- Most developers only have **Contributor** role
- Contributor can create resources but NOT assign permissions

### Impact
- **AKS LoadBalancer stuck**: Cannot get External IP without Network Contributor role
- **Key Vault access blocked**: n8n cannot read encryption keys without Secrets User role

### Solution
**Option 1: Manual role assignment (recommended for non-admins)**
```bash
# Ask your Azure admin to run:
az role assignment create \
  --role "Network Contributor" \
  --assignee <AKS-MANAGED-IDENTITY-ID> \
  --scope /subscriptions/<SUB-ID>/resourceGroups/<RG-NAME>
```

**Option 2: Comment out in Terraform (for teams without admin access)**
```terraform
# Commented out - requires elevated permissions
# Uncomment if you have "User Access Administrator" or "Owner" role
# resource "azurerm_role_assignment" "aks_network_contributor" {
#   scope                = azurerm_resource_group.main.id
#   role_definition_name = "Network Contributor"
#   principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
# }
```

**Option 3: Use custom role with delegation** (enterprise solution)
- Create a custom role with just `roleAssignments/write` for specific scopes
- Delegate this custom role to deployment service principals

### Required Role Assignments
```bash
# 1. For LoadBalancer to work
az role assignment create \
  --role "Network Contributor" \
  --assignee $(az aks show -g <RG> -n <CLUSTER> --query "identity.principalId" -o tsv) \
  --scope /subscriptions/<SUB-ID>/resourceGroups/<RG>

# 2. For Key Vault access
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $(az aks show -g <RG> -n <CLUSTER> --query "addonProfiles.azureKeyvaultSecretsProvider.identity.objectId" -o tsv) \
  --scope $(az keyvault show -g <RG> -n <KV-NAME> --query id -o tsv)
```

### Lessons Learned
1. **Separate permissions from infrastructure**: Role assignments should be handled by admins
2. **Document manual steps clearly**: Provide exact commands for admins
3. **Use service principals for CI/CD**: Gives more control over permissions
4. **Validate permissions early**: Check role assignments in Terraform plan phase
5. **Expect 403s in multi-user environments**: Not everyone has Owner/UAA roles

---

## Challenge 5: Terraform Kubernetes Provider Connection

### Problem
```
Error: Get "http://localhost/apis/storage.k8s.io/v1/storageclasses":
dial tcp 127.0.0.1:80: connection refused
```

**Code that failed:**
```terraform
data "azurerm_kubernetes_cluster" "main" {
  name                = azurerm_kubernetes_cluster.main.name  # ❌ Circular reference
  resource_group_name = azurerm_resource_group.main.name
  depends_on          = [azurerm_kubernetes_cluster.main]
}
```

### Root Cause
- Terraform Kubernetes/Helm providers need cluster credentials **during plan phase**
- Using `azurerm_kubernetes_cluster.main.name` creates a circular dependency
- Providers initialize before resources are created

### Solution
Use variables instead of resource references:

```terraform
data "azurerm_kubernetes_cluster" "main" {
  name                = var.cluster_name        # ✅ Use variable
  resource_group_name = var.resource_group_name # ✅ Use variable
}

provider "kubernetes" {
  host                   = data.azurerm_kubernetes_cluster.main.kube_config[0].host
  client_certificate     = base64decode(data.azurerm_kubernetes_cluster.main.kube_config[0].client_certificate)
  client_key             = base64decode(data.azurerm_kubernetes_cluster.main.kube_config[0].client_key)
  cluster_ca_certificate = base64decode(data.azurerm_kubernetes_cluster.main.kube_config[0].cluster_ca_certificate)
}
```

### Alternative: Separate Terraform State
For production, consider splitting into 2 Terraform states:
1. **Infrastructure**: VNet, AKS cluster, Key Vault
2. **Applications**: Helm charts, Kubernetes resources

```bash
# State 1: infrastructure/
terraform apply

# State 2: applications/
terraform apply
```

### Lessons Learned
1. **Providers need data at plan time**: Can't reference resources being created
2. **Use data sources with variables**: Avoids circular dependencies
3. **Consider state separation**: Infrastructure vs. applications
4. **Test with small configs first**: Validate provider connections early

---

## Challenge 6: Helm Release Timeouts and Failed Status

### Problem
```
Warning: Helm release "" was created but has a failed status.
Error: context deadline exceeded
```

**Helm deployment stuck:**
- Pods running successfully
- LoadBalancer service stuck in `<pending>` state
- Helm waited 10+ minutes then timed out

### Root Cause
**LoadBalancer couldn't get External IP because:**
1. Missing Network Contributor role (see Challenge #4)
2. Service tried to use pre-allocated Public IP without permissions

```terraform
service:
  loadBalancerIP: "${loadbalancer_ip}"  # Tries to use specific IP
  annotations:
    service.beta.kubernetes.io/azure-pip-name: "${loadbalancer_ip}"
```

### Solution
**Immediate fix:**
```bash
# Delete failed Helm release
helm uninstall ingress-nginx -n ingress-nginx

# Grant Network Contributor role (admin required)
az role assignment create --role "Network Contributor" \
  --assignee <AKS-IDENTITY> \
  --scope /subscriptions/<SUB>/resourceGroups/<RG>

# Retry Terraform apply
terraform apply
```

**Long-term fix:**
- Grant permissions before deploying Helm charts
- Use `wait = false` in Terraform helm_release for debugging
- Monitor LoadBalancer events:
  ```bash
  kubectl describe svc ingress-nginx-controller -n ingress-nginx
  ```

### Lessons Learned
1. **Grant permissions first**: Don't deploy Helm charts without proper roles
2. **Check service events**: `kubectl describe svc` shows permission errors
3. **Set reasonable timeouts**: Default 10min may not be enough for troubleshooting
4. **LoadBalancer issues != Helm issues**: Helm succeeded, Azure permissions failed

---

## Challenge 7: Helm Release Name Conflicts

### Problem
```
Error: cannot re-use a name that is still in use
```

### Root Cause
- Failed Helm release left orphaned metadata in Kubernetes
- Terraform lost track of release state
- Kubernetes still has release name reserved

### Solution
```bash
# List all Helm releases (including failed ones)
helm list -A --all

# Uninstall the stuck release
helm uninstall <RELEASE-NAME> -n <NAMESPACE>

# Retry Terraform
terraform apply
```

**Prevention in Terraform:**
```terraform
resource "helm_release" "nginx_ingress" {
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  namespace        = "ingress-nginx"
  create_namespace = true

  # Add these for better reliability
  timeout          = 600
  atomic           = true  # Rollback on failure
  cleanup_on_fail  = true  # Clean up on failure
  force_update     = true  # Force update if needed
}
```

### Lessons Learned
1. **Use `atomic = true`**: Auto-rollback prevents stuck releases
2. **Set `cleanup_on_fail = true`**: Automatic cleanup on errors
3. **Monitor Helm state**: Don't assume Terraform knows everything
4. **Manual cleanup is sometimes needed**: `helm uninstall` is your friend

---

## Best Practices & Recommendations

### 1. Infrastructure Design
- ✅ **Omit zones for portability**: Let Azure handle zone distribution
- ✅ **Use latest supported K8s versions**: Avoid LTS-only versions
- ✅ **Separate network and app infrastructure**: Different Terraform states
- ✅ **Use managed identities**: Avoid storing credentials

### 2. Permission Management
- ✅ **Document required role assignments**: Provide exact `az` commands
- ✅ **Grant permissions before deployment**: Prevents Helm failures
- ✅ **Use least-privilege roles**: Network Contributor, not Owner
- ✅ **Verify identity access**: Check `az aks show --query identity`

### 3. Terraform Best Practices
- ✅ **Use variables in data sources**: Avoid circular dependencies
- ✅ **Separate infra and apps**: Different state files
- ✅ **Set Helm timeouts appropriately**: 600s+ for complex charts
- ✅ **Enable Helm atomic/cleanup**: `atomic = true`, `cleanup_on_fail = true`

### 4. Debugging Workflow
```bash
# 1. Check Azure CLI authentication
az account show

# 2. Verify AKS cluster
az aks show -g <RG> -n <CLUSTER> --query "provisioningState"

# 3. Get kubeconfig
az aks get-credentials -g <RG> -n <CLUSTER> --overwrite-existing

# 4. Check node status
kubectl get nodes

# 5. Check service events
kubectl describe svc <SVC-NAME> -n <NAMESPACE>

# 6. View Helm releases
helm list -A --all

# 7. Check role assignments
az role assignment list --scope /subscriptions/<SUB>/resourceGroups/<RG>
```

### 5. Common Commands Reference
```bash
# Check available K8s versions
az aks get-versions --location eastus --output table

# Get AKS managed identity
az aks show -g <RG> -n <CLUSTER> --query "identity.principalId" -o tsv

# Get Key Vault addon identity
az aks show -g <RG> -n <CLUSTER> \
  --query "addonProfiles.azureKeyvaultSecretsProvider.identity.objectId" -o tsv

# Verify LoadBalancer
kubectl get svc -n ingress-nginx
kubectl describe svc ingress-nginx-controller -n ingress-nginx

# Debug Helm release
helm status <RELEASE> -n <NAMESPACE>
helm get values <RELEASE> -n <NAMESPACE>

# Clean up failed Helm release
helm uninstall <RELEASE> -n <NAMESPACE>
```

---

## Azure vs AWS Key Differences

| Aspect | AWS EKS | Azure AKS |
|--------|---------|-----------|
| **Zones** | Explicit multi-zone (`["us-east-1a", "us-east-1b"]`) | Zone-redundant (omit parameter) or single zone |
| **K8s Versions** | All versions on standard tier | Some versions LTS-only (Premium tier required) |
| **Role Management** | IAM roles auto-attached | Managed identities need manual role assignments |
| **Load Balancer** | ELB auto-provisions | Needs Network Contributor role |
| **Secrets** | AWS Secrets Manager integration | Key Vault with addon identity |
| **Region Consistency** | High zone consistency | Variable zone support by region |
| **Provider Init** | Works with resource refs | Requires data sources with variables |

---

## Conclusion

Azure AKS deployment has unique challenges compared to AWS EKS:

**Key Takeaways:**
1. **Zone handling is different**: Use zone-redundant where possible
2. **Permissions are strict**: Expect to involve admins for role assignments
3. **Version support varies**: Check K8s version compatibility with tier
4. **Provider initialization is strict**: Use data sources carefully
5. **Debugging is iterative**: Expect permission errors, not just config errors

**Success Factors:**
- Understanding Azure's permission model (RBAC)
- Designing for cross-region portability (omit zones)
- Separating infrastructure concerns (Terraform states)
- Having admin support for role assignments
- Thorough testing in target regions

This deployment taught valuable lessons about multi-cloud portability and Azure-specific constraints. The documented solutions should help others avoid these pitfalls.

---

**Last Updated**: October 18, 2025
**Terraform Version**: 1.6+
**Azure Provider**: ~> 3.80
**Region Tested**: East US
