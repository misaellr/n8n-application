# Azure Permissions Explained

## Overview

Your AKS deployment requires **2 role assignments** for the cluster's managed identity.

## 1. Network Contributor Role

### What It Is
A built-in Azure role that grants permissions to manage network resources.

### Who Needs It
- **Principal:** AKS Cluster Managed Identity
- **Principal ID:** `ce3cba67-e83b-42ab-97ff-40b6edc8c709`
- **Scope:** Resource Group `n8n-rg`

### What It Allows

The Network Contributor role grants these specific permissions within the resource group:

```
Microsoft.Network/virtualNetworks/read
Microsoft.Network/virtualNetworks/subnets/read
Microsoft.Network/virtualNetworks/subnets/join/action  ← THIS IS THE CRITICAL ONE
Microsoft.Network/publicIPAddresses/read
Microsoft.Network/publicIPAddresses/write
Microsoft.Network/publicIPAddresses/join/action
Microsoft.Network/loadBalancers/read
Microsoft.Network/loadBalancers/write
Microsoft.Network/networkInterfaces/read
Microsoft.Network/networkInterfaces/write
```

### Why You Need It

**Current Problem:**
Your nginx-ingress LoadBalancer needs to:
1. Create a LoadBalancer resource in Azure
2. Attach it to the VNet subnet
3. Associate it with nodes in the AKS cluster

**The Error:**
```
LinkedAuthorizationFailed: does not have permission to perform action
'Microsoft.Network/virtualNetworks/subnets/join/action'
```

**Without this permission:**
- ❌ LoadBalancer stays in `<pending>` state forever
- ❌ Can't get external IP address
- ❌ No external access to n8n
- ❌ No ingress routing works

**With this permission:**
- ✅ LoadBalancer gets created in Azure
- ✅ Gets assigned external IP (from Azure's pool)
- ✅ Attaches to your VNet subnet
- ✅ Routes traffic from internet → LoadBalancer → nginx-ingress → n8n pods

### Security Implications

**What the AKS cluster CAN do with this role:**
- Create/modify/delete network interfaces
- Create/modify/delete load balancers
- Create/modify/delete public IPs
- Join VNet subnets
- Manage Network Security Groups

**What the AKS cluster CANNOT do:**
- Access other resource groups (scope limited to `n8n-rg`)
- Modify VMs or storage
- Access Key Vault secrets (requires separate permission)
- Create/delete VNets (can only use existing ones)
- Manage IAM roles

**Is it safe?**
✅ Yes, this is standard for AKS deployments with custom networking
✅ Scope is limited to your resource group only
✅ Required for any LoadBalancer service in AKS

---

## 2. Key Vault Secrets User Role

### What It Is
A built-in Azure role that grants read-only access to Key Vault secrets.

### Who Needs It
- **Principal:** AKS Key Vault Secrets Provider Identity
- **Principal ID:** `24a0f03c-297e-426a-9173-ba374f5a440c`
- **Scope:** Key Vault `n8n-app-kv-67885b65`

### What It Allows

```
Microsoft.KeyVault/vaults/secrets/getSecret/action
Microsoft.KeyVault/vaults/secrets/readMetadata/action
```

### Why You Need It

Your deployment stores sensitive data in Azure Key Vault:
- Database connection string
- Database password
- N8N encryption key

**Without this permission:**
- ❌ Pods can't read secrets from Key Vault
- ❌ Database connection fails
- ❌ N8N can't start (missing encryption key)

**With this permission:**
- ✅ AKS CSI Secret Store driver can read secrets
- ✅ Secrets mounted as volumes in pods
- ✅ N8N can connect to database
- ✅ Secure secret management (not in environment variables)

### Security Implications

**What the secrets provider CAN do:**
- Read secret values from Key Vault
- Read secret metadata (names, versions)

**What the secrets provider CANNOT do:**
- Modify or delete secrets
- Create new secrets
- Access other Key Vaults (scope limited to your specific vault)
- Grant access to others
- Change Key Vault configuration

**Is it safe?**
✅ Yes, this is the recommended way to use secrets in AKS
✅ Read-only access (can't modify secrets)
✅ Scope limited to one specific Key Vault
✅ Better than storing secrets in environment variables or Kubernetes secrets

---

## Why These Aren't Granted Automatically

### Permission Model

Azure follows the **principle of least privilege**:
- Resources are created with minimal permissions
- You must explicitly grant additional permissions
- This prevents accidental security issues

### Why You Need Elevated Permissions to Grant These

To assign roles, you need **one of these**:
- `Owner` role on the resource group
- `User Access Administrator` role on the subscription
- `Role Based Access Control Administrator` role

**You have:** Contributor role (can create resources, but not assign roles)
**You need:** Owner or User Access Administrator (can assign roles)

### Why Terraform Can't Do It Automatically

Terraform runs with **your** Azure credentials. If you don't have permission to assign roles, Terraform can't do it either.

**Options:**
1. Ask admin to grant you elevated permissions (temporarily)
2. Ask admin to run the role assignment commands
3. Use `terraform_manage_role_assignments = false` (current solution)

---

## Command Breakdown

### Network Contributor Command

```bash
az role assignment create \
  --role "Network Contributor" \
  --assignee ce3cba67-e83b-42ab-97ff-40b6edc8c709 \
  --scope /subscriptions/013c5d82-8670-4c50-81d1-1c84a77a8303/resourceGroups/n8n-rg
```

**What this does:**
- `--role "Network Contributor"` - The built-in role to assign
- `--assignee ce3cba67-e83b-42ab-97ff-40b6edc8c709` - Your AKS cluster's identity
- `--scope /subscriptions/.../resourceGroups/n8n-rg` - Limited to your resource group only

### Key Vault Secrets User Command

```bash
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee 24a0f03c-297e-426a-9173-ba374f5a440c \
  --scope /subscriptions/013c5d82-8670-4c50-81d1-1c84a77a8303/resourceGroups/n8n-rg/providers/Microsoft.KeyVault/vaults/n8n-app-kv-67885b65
```

**What this does:**
- `--role "Key Vault Secrets User"` - Read-only access to secrets
- `--assignee 24a0f03c-297e-426a-9173-ba374f5a440c` - Your AKS secrets provider identity
- `--scope .../vaults/n8n-app-kv-67885b65` - Limited to your specific Key Vault only

---

## Verification After Assignment

After admin grants these permissions, verify with:

```bash
# Check Network Contributor role
az role assignment list \
  --assignee ce3cba67-e83b-42ab-97ff-40b6edc8c709 \
  --scope /subscriptions/013c5d82-8670-4c50-81d1-1c84a77a8303/resourceGroups/n8n-rg

# Should show:
# - Role: Network Contributor
# - Principal: ce3cba67-e83b-42ab-97ff-40b6edc8c709
# - Scope: /subscriptions/.../resourceGroups/n8n-rg

# Check Key Vault Secrets User role
az role assignment list \
  --assignee 24a0f03c-297e-426a-9173-ba374f5a440c \
  --scope /subscriptions/013c5d82-8670-4c50-81d1-1c84a77a8303/resourceGroups/n8n-rg/providers/Microsoft.KeyVault/vaults/n8n-app-kv-67885b65

# Should show:
# - Role: Key Vault Secrets User
# - Principal: 24a0f03c-297e-426a-9173-ba374f5a440c
# - Scope: .../vaults/n8n-app-kv-67885b65
```

---

## Common Questions

### Q: Why two different identities?

**A:** AKS uses multiple managed identities for different purposes:

1. **Cluster Identity** (`ce3cba67-...`)
   - Used by the control plane
   - Manages cluster infrastructure (load balancers, disks, etc.)
   - Needs Network Contributor

2. **Kubelet Identity** (node pool identity)
   - Used by worker nodes
   - Pulls container images, manages node resources

3. **Key Vault Secrets Provider Identity** (`24a0f03c-...`)
   - Specialized add-on for Key Vault integration
   - Only reads secrets from Key Vault
   - Needs Key Vault Secrets User

### Q: Can I use less privileged roles?

**A:** Not really. These are the **minimum** required roles:

- Network Contributor is needed for LoadBalancer (no narrower built-in role exists)
- Key Vault Secrets User is read-only (already least privilege)

You could create custom roles with fewer permissions, but it's complex and not recommended.

### Q: What happens if I only grant Network Contributor?

**A:**
- ✅ LoadBalancer will get external IP
- ❌ N8N pods will fail to start (can't read database credentials from Key Vault)

Both are required for a working deployment.

### Q: What happens if I only grant Key Vault Secrets User?

**A:**
- ✅ N8N can read secrets
- ❌ LoadBalancer stuck in `<pending>` (no external access)

Both are required for a working deployment.

---

## Alternative: Using Dynamic IP Without Permissions

**Is there a way to avoid needing Network Contributor?**

Unfortunately, **no**. Even with dynamic IP allocation:
- LoadBalancer still needs to attach to VNet subnet
- Still requires `Microsoft.Network/virtualNetworks/subnets/join/action`
- Network Contributor is required regardless of static vs dynamic IP

**The only way to avoid it:** Don't use LoadBalancer at all
- Disable nginx-ingress
- Use NodePort or port-forward instead
- Not recommended for production

---

## Security Best Practices

After deployment, consider:

1. **Monitor role assignments:**
   ```bash
   az role assignment list --scope /subscriptions/.../resourceGroups/n8n-rg
   ```

2. **Review regularly:**
   - Remove any unnecessary role assignments
   - Audit who has Owner/Contributor access

3. **Use Azure Policy:**
   - Enforce required tags
   - Restrict resource types
   - Require encryption

4. **Enable diagnostic logs:**
   - Track Key Vault access
   - Monitor network changes
   - Alert on suspicious activity

---

## Summary

| Role | Who Needs It | Scope | Why | Safe? |
|------|--------------|-------|-----|-------|
| **Network Contributor** | AKS Cluster Identity | Resource Group `n8n-rg` | Create/manage LoadBalancer and attach to VNet | ✅ Yes - Standard for AKS |
| **Key Vault Secrets User** | Key Vault Secrets Provider | Key Vault `n8n-app-kv-67885b65` | Read database credentials and encryption key | ✅ Yes - Read-only access |

**Both permissions are:**
- ✅ Required for your deployment
- ✅ Standard practice for AKS
- ✅ Properly scoped (limited to specific resources)
- ✅ Following least privilege principle
- ✅ Safe to grant

**Your admin should feel comfortable granting these** - they're not excessive or unusual for an AKS deployment.
