# GCP Skip-Terraform Mode Lessons Learned

## Date: October 28, 2025

### Incident: Multiple Issues During GCP Skip-Terraform Deployment

---

## Summary

After successfully deploying GCP infrastructure with Terraform, the `--skip-terraform` mode encountered 5 distinct issues before completing successfully. Each issue revealed gaps in the GCPDeploymentConfig class, skip-terraform logic, and multi-cloud kubectl context management. This document captures all issues, root causes, and fixes for future reference.

---

## Background

### What Happened

1. ✅ **Terraform Phase** completed successfully (separate session)
   - All GCP infrastructure deployed: VPC, GKE cluster, Cloud SQL, etc.
   - 26 resources created
   - terraform.tfvars saved with configuration

2. ❌ **Skip-Terraform Phase** encountered 5 sequential failures:
   - Issue #1: Missing n8n_host in terraform.tfvars
   - Issue #2: Wrong configuration class returned
   - Issue #3: Encryption key not found
   - Issue #4: Missing timezone attribute
   - Issue #5: kubectl context pointing to wrong cluster

3. ✅ **Resolution** after all fixes:
   - n8n deployed successfully to GKE
   - nginx ingress controller installed
   - Application accessible via LoadBalancer IP

---

## Issues Encountered

### Issue #1: Missing n8n_host in terraform.tfvars

**Error:**
```
✗ Unable to load existing configuration: n8n_host is missing in terraform.tfvars
```

**Root Cause:**
The terraform.tfvars file generated during initial Terraform deployment didn't include the `n8n_host` field. This was missing from the automated tfvars generation.

**Fix:**
Manually added to terraform.tfvars:
```hcl
n8n_host = "n8n-gcp.lrproducthub.com"
```

**Status:** ✅ Fixed in terraform.tfvars
**Prevention:** Terraform tfvars generation should include all required application fields

---

### Issue #2: Wrong Configuration Class Type Returned

**Error:**
Still getting "n8n_host is missing" even after adding the field.

**Root Cause:**
The `load_existing_configuration()` function in setup.py (line 2035) always returned `DeploymentConfig` (AWS class) regardless of the `cloud_provider` parameter. This meant:
- GCP-specific fields like `gcp_project_id` didn't exist on the object
- Fields were being parsed but discarded
- The wrong config type was passed to subsequent functions

**Code Before:**
```python
def load_existing_configuration(script_dir: Path, cloud_provider: str = "aws"):
    """Load deployment values from terraform/{cloud_provider}/terraform.tfvars"""
    # ... parsing logic ...

    # BUG: Always returned AWS config
    config = DeploymentConfig()

    # Parsed values into AWS config
    for key, parsed in parsed_vars.items():
        if key == 'gcp_project_id':  # This would fail since AWS config has no such field
            config.gcp_project_id = str(parsed)
```

**Code After:**
```python
def load_existing_configuration(script_dir: Path, cloud_provider: str = "aws"):
    """Load deployment values from terraform/{cloud_provider}/terraform.tfvars"""
    # ... parsing logic ...

    # FIX: Return correct config class based on cloud provider
    if cloud_provider == "gcp":
        config = GCPDeploymentConfig()
    elif cloud_provider == "azure":
        config = AzureDeploymentConfig()
    else:
        config = DeploymentConfig()

    # Parse values into appropriate config object
    for key, parsed in parsed_vars.items():
        if key == 'gcp_project_id':
            if hasattr(config, 'gcp_project_id'):
                config.gcp_project_id = str(parsed)
        elif key == 'gcp_region':
            if hasattr(config, 'gcp_region'):
                config.gcp_region = str(parsed)
        # ... more GCP fields ...
```

**Commit:** e79c331 - "fix: load correct config class in load_existing_configuration for GCP/Azure"

**Status:** ✅ Fixed in setup.py:2035-2125
**Prevention:** Add unit tests for load_existing_configuration with different cloud providers

---

### Issue #3: Encryption Key Not Found in Terraform Outputs

**Error:**
```
Failed to retrieve encryption key from Terraform outputs
```

**Root Cause:**
GCP stores the n8n encryption key in Secret Manager for security, not as a Terraform output. AWS and Azure expose it as an output, but GCP intentionally doesn't. The skip-terraform logic only checked outputs, not the config object (which has the key from terraform.tfvars).

**Security Context:**
- AWS/Azure: Encryption key exposed in Terraform outputs (less secure)
- GCP: Encryption key stored in Secret Manager, not in outputs (more secure)
- The key exists in terraform.tfvars but wasn't being used as a fallback

**Code Before:**
```python
# Get encryption key from outputs
encryption_key = outputs.get('n8n_encryption_key_value', '')
if not encryption_key:
    raise Exception("Failed to retrieve encryption key from Terraform outputs")
```

**Code After:**
```python
# Get encryption key from outputs (AWS/Azure) or config (GCP stores in Secret Manager)
encryption_key = outputs.get('n8n_encryption_key_value', '')
if not encryption_key and hasattr(config, 'n8n_encryption_key'):
    encryption_key = config.n8n_encryption_key

if not encryption_key:
    raise Exception("Failed to retrieve encryption key from Terraform outputs or configuration")
```

**Commit:** 7fcaca5 - "fix: add fallback for encryption key from config in skip-terraform mode"

**Status:** ✅ Fixed in setup.py:5051-5058
**Prevention:** Document GCP's security model difference in skip-terraform logic

---

### Issue #4: Missing timezone and n8n_persistence_size Attributes

**Error:**
```
AttributeError: 'GCPDeploymentConfig' object has no attribute 'timezone'
```

**Root Cause:**
The `GCPDeploymentConfig` class was incomplete. The `deploy_n8n()` function expects certain common attributes that exist on AWS and Azure config classes but were missing from GCP:
- `timezone` - Used to set TZ environment variables
- `n8n_persistence_size` - Used to set PVC size

This happened because GCPDeploymentConfig was created by copying only the GCP-specific parts from AWS config, not the common application fields.

**Code Before:**
```python
class GCPDeploymentConfig:
    def __init__(self):
        # ... GCP-specific fields ...
        self.n8n_namespace: str = "n8n"
        self.n8n_host: str = ""
        self.n8n_protocol: str = "http"
        self.n8n_encryption_key: str = ""
        # MISSING: timezone, n8n_persistence_size
```

**Code After:**
```python
class GCPDeploymentConfig:
    def __init__(self):
        # ... GCP-specific fields ...
        self.n8n_namespace: str = "n8n"
        self.n8n_host: str = ""
        self.n8n_protocol: str = "http"
        self.n8n_encryption_key: str = ""
        self.n8n_persistence_size: str = "10Gi"  # ADDED
        self.timezone: str = "America/New_York"  # ADDED
```

**Commit:** ec45cb9 - "fix: add missing timezone and persistence_size to GCPDeploymentConfig"

**Status:** ✅ Fixed in setup.py:339-340, 372-373
**Prevention:** Create a base configuration class with common fields, have cloud-specific classes inherit from it

---

### Issue #5: kubectl Context Pointing to Wrong Cluster (Multi-Cloud Issue)

**Error:**
```
Error: INSTALLATION FAILED: admission webhook "vingress.elbv2.k8s.aws" denied the request:
invalid ingress class: IngressClass.networking.k8s.io "nginx" not found
```

**Root Cause:**
The kubectl context had switched back to AWS EKS cluster (`cn-dxps-eks`) instead of staying on GCP GKE cluster (`gke_cross-cloud-475812_us-central1_n8n-gke-cluster`). This happened because:

1. **Multi-cluster environment**: User has 8+ Kubernetes clusters configured:
   - 3 AWS EKS clusters
   - 2 Azure AKS clusters
   - 1 GCP GKE cluster
   - 2 local clusters (k3d, magnolia)

2. **Context switching**: Some external command or script switched the context between setup.py operations

3. **No verification**: The skip-terraform mode didn't verify or explicitly set the kubectl context before Helm deployment

**Discovery Process:**
1. Error mentioned AWS admission webhook (vingress.elbv2.k8s.aws)
2. Checked `kubectl config current-context` - showed AWS EKS
3. Checked `kubectl get ingressclass` - only showed ALB (AWS), no nginx
4. Consulted OpenAI for root cause and best practices
5. Manually switched context with `kubectl config use-context gke_...`

**Code Fix:**
Added kubectl context verification and switching in skip-terraform section (line 4876):

```python
# Verify and switch kubectl context to target cluster
print(f"\n{Colors.HEADER}🔍 Verifying kubectl context...{Colors.ENDC}")

# Determine expected context name based on cloud provider
if cloud_provider == "gcp":
    # GKE context format: gke_PROJECT_REGION_CLUSTER
    expected_context = f"gke_{config.gcp_project_id}_{config.gcp_region}_{config.cluster_name}"
elif cloud_provider == "azure":
    # AKS context is just the cluster name
    expected_context = config.cluster_name
else:  # AWS
    # EKS context format includes account ID, but we can match on cluster name
    expected_context = config.cluster_name

# Get current context
result = subprocess.run(['kubectl', 'config', 'current-context'],
                       capture_output=True, text=True)
current_context = result.stdout.strip()

# Verify or switch context
if expected_context not in current_context:
    print(f"{Colors.WARNING}⚠  kubectl context mismatch{Colors.ENDC}")
    print(f"  Current: {current_context}")
    print(f"  Expected context containing: {expected_context}")

    # List available contexts and find the matching one
    result = subprocess.run(['kubectl', 'config', 'get-contexts', '-o', 'name'],
                           capture_output=True, text=True)
    available_contexts = result.stdout.strip().split('\n')

    # Find the context that matches our cluster
    target_context = None
    for ctx in available_contexts:
        if expected_context in ctx:
            target_context = ctx
            break

    if not target_context:
        print(f"{Colors.FAIL}✗ Could not find matching kubectl context{Colors.ENDC}")
        print(f"\n{Colors.WARNING}Available contexts:{Colors.ENDC}")
        for ctx in available_contexts:
            print(f"  - {ctx}")
        raise Exception("kubectl context not found - run the configure_kubectl command manually")

    print(f"\n{Colors.HEADER}Switching kubectl context...{Colors.ENDC}")
    result = subprocess.run(['kubectl', 'config', 'use-context', target_context],
                           capture_output=True, text=True)
    if result.returncode == 0:
        print(f"{Colors.OKGREEN}✓ Switched to {target_context}{Colors.ENDC}")
    else:
        print(f"{Colors.FAIL}✗ Failed to switch context{Colors.ENDC}")
        raise Exception("kubectl context switch required")
else:
    print(f"{Colors.OKGREEN}✓ kubectl context correct: {current_context}{Colors.ENDC}")
```

**Commit:** 2f41c8c - "fix: add kubectl context verification and switching for multi-cloud deployments"

**Status:** ✅ Fixed in setup.py:4876-4931
**Prevention:** Always verify kubectl context before any kubectl/helm operations in automation

**OpenAI Recommendation:**
> "Explicitly set the context when possible. This can be done using the `kubectl config use-context` command to ensure you're interacting with the intended cluster."

---

### Issue #6: Missing tls_certificate_source Attribute (Bonus Issue)

**Error:**
```
AttributeError: 'GCPDeploymentConfig' object has no attribute 'tls_certificate_source'
```

**Root Cause:**
After fixing Issue #5, another missing attribute was discovered. The AWS and Azure config classes have `tls_certificate_source` for TLS configuration, but GCP was missing it. This field is checked at the end of deployment (line 5187).

**Code Fix:**
```python
class GCPDeploymentConfig:
    def __init__(self):
        # ... other fields ...

        # TLS settings (matches AWS/Azure pattern)
        self.enable_tls: bool = False
        self.tls_provider: str = "letsencrypt"
        self.tls_certificate_source: str = "none"  # ADDED: "none", "byo", or "letsencrypt"
        self.letsencrypt_email: str = ""
```

**Commit:** 3151e63 - "fix: add missing tls_certificate_source attribute to GCPDeploymentConfig"

**Status:** ✅ Fixed in setup.py:345, 376
**Prevention:** Same as Issue #4 - need base configuration class

---

## Additional Issue: GKE Cluster Resource Constraints

### Problem

After the kubectl context was fixed, the nginx ingress controller pod failed to schedule with error:
```
Warning: FailedScheduling - 0/3 nodes are available: 3 Insufficient cpu.
preemption: 0/3 nodes are available: 3 No preemption victims found for incoming pod.
```

### Root Cause

GKE clusters come with many system pods (monitoring, logging, networking, etc.) that consume CPU resources:
- 3x e2-medium nodes (2 vCPU each = 2000m CPU)
- System pods consuming 91-99% of CPU requests
- nginx ingress controller requesting 100m CPU
- Not enough room for new pod

**System Pods Breakdown (per node, ~23 pods):**
- GKE metrics and monitoring: gmp-operator, collector, gke-metrics-agent
- Networking: Calico CNI, node-local-dns, kube-proxy, netd
- Storage: pdcsi-node (persistent disk CSI)
- Logging: fluentbit-gke
- Autoscalers: calico-typha-horizontal-autoscaler, calico-node-vertical-autoscaler, konnectivity-agent-autoscaler
- Others: kube-dns, l7-default-backend, metadata-server, ip-masq-agent

### Solution

Reinstalled nginx ingress controller with lower resource requests:

```bash
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --set controller.service.type=LoadBalancer \
  --set controller.resources.requests.cpu=50m \      # Reduced from 100m
  --set controller.resources.requests.memory=64Mi \  # Reduced from 90Mi
  --timeout 10m --wait
```

**Result:** ✅ Pod scheduled successfully

### Recommendations

**For Production:**
1. Use larger node types (e2-standard-2, e2-standard-4, or n2-standard-2)
2. Enable cluster autoscaling
3. Use separate node pools for application vs system workloads
4. Monitor resource usage and right-size

**For Development:**
- Minimum node type for GKE: e2-medium (2 vCPU, 4GB RAM)
- Accept that ~1000m CPU will be consumed by system pods
- Use lower resource requests for dev workloads
- Consider e2-small only for very minimal testing (not recommended for GKE)

---

## Final Deployment Result

**Status:** ✅ SUCCESS

```
n8n GCP Deployment Status
========================================

✓ Infrastructure: Deployed (Terraform)
  - GKE Cluster: n8n-gke-cluster
  - Region: us-central1
  - Nodes: 3x e2-medium (2 vCPU, 4GB RAM each)

✓ Application: Deployed (Helm)
  - n8n pod: Running
  - Namespace: n8n
  - Database: SQLite (file-based)

✓ Ingress: Configured
  - Controller: nginx-ingress
  - LoadBalancer IP: 136.114.23.83
  - Status: HTTP 200 OK

✓ Access:
  - curl -H "Host: n8n-gcp.lrproducthub.com" http://136.114.23.83
  - Returns: HTTP/1.1 200 OK

⚠ DNS Setup Required:
  n8n-gcp.lrproducthub.com -> 136.114.23.83
```

---

## Key Lessons Learned

### 1. Configuration Class Design Issues

**Problem:** GCPDeploymentConfig was created by copying code, not by inheriting from a base class
**Impact:** Missing attributes caused 3 separate failures (timezone, persistence_size, tls_certificate_source)

**Recommendation:**
Create a base `BaseDeploymentConfig` class with common fields:
```python
class BaseDeploymentConfig:
    def __init__(self):
        # Common application fields
        self.n8n_namespace: str = "n8n"
        self.n8n_host: str = ""
        self.n8n_encryption_key: str = ""
        self.n8n_persistence_size: str = "10Gi"
        self.timezone: str = "America/New_York"
        self.enable_tls: bool = False
        self.tls_certificate_source: str = "none"
        # ...

class GCPDeploymentConfig(BaseDeploymentConfig):
    def __init__(self):
        super().__init__()
        # GCP-specific fields only
        self.gcp_project_id: str = ""
        self.gcp_region: str = "us-central1"
        # ...
```

### 2. Cloud-Specific Security Models

**Issue:** GCP handles secrets differently than AWS/Azure
**Impact:** Encryption key not found in Terraform outputs

**Key Difference:**
- AWS/Azure: Secrets in Terraform state/outputs (convenience > security)
- GCP: Secrets in Secret Manager (security > convenience)

**Recommendation:** Always implement fallback logic for cloud-specific security models

### 3. Multi-Cloud kubectl Context Management

**Issue:** kubectl context switched between clouds unexpectedly
**Impact:** Complete deployment failure with confusing error messages

**Root Cause:** Working with 8+ Kubernetes clusters without explicit context management

**Best Practices:**
1. **Always verify context** before operations: `kubectl config current-context`
2. **Explicitly switch context** at start of deployment
3. **Use --context flag** for one-off commands: `kubectl --context=gke_... get pods`
4. **Document context requirements** in user instructions
5. **Add context verification** to all automation scripts

**User's Note:**
> "remember to always use local context when running helm command. I have multiple projects running on different clouds."

### 4. GKE Resource Overhead

**Issue:** GKE system pods consume significant resources
**Impact:** Standard workload resource requests fail on small nodes

**Key Finding:**
- e2-medium (2 vCPU): ~1000m (50%) consumed by system pods
- e2-small (2 vCPU): ~1000m (50%) consumed - leaves only 1 vCPU for apps (not recommended)
- e2-standard-2 (2 vCPU): Same overhead but more memory

**Recommendation:**
- Development: e2-medium minimum, lower app resource requests
- Production: e2-standard-2 or n2-standard-2, enable autoscaling
- Document GKE resource overhead in requirements

### 5. Skip-Terraform Mode Assumptions

**Issues Found:**
1. Assumed config class type based on parameter (but always returned AWS)
2. Assumed encryption key in outputs (but GCP uses Secret Manager)
3. Assumed kubectl context would be correct (but multi-cloud environments)
4. Assumed config class had all required attributes (but GCP incomplete)

**Recommendation:**
- Add comprehensive validation at start of skip-terraform mode
- Check all required attributes exist on config object
- Verify kubectl context before operations
- Document cloud-specific differences clearly

---

## Timeline of Fixes

1. **Oct 28, 06:00** - Added n8n_host to terraform.tfvars (manual fix)
2. **Oct 28, 06:15** - Fixed load_existing_configuration() class selection (commit e79c331)
3. **Oct 28, 06:25** - Added encryption key fallback logic (commit 7fcaca5)
4. **Oct 28, 06:35** - Added timezone and persistence_size (commit ec45cb9)
5. **Oct 28, 06:45** - Added kubectl context verification (commit 2f41c8c)
6. **Oct 28, 06:50** - Added tls_certificate_source (commit 3151e63)
7. **Oct 28, 07:00** - Installed nginx ingress with reduced resources
8. **Oct 28, 07:05** - Deployment successful, n8n accessible

**Total Time:** ~1 hour 5 minutes (excluding initial GCP infrastructure deployment)
**Total Issues:** 6 (5 code issues + 1 resource constraint)
**Total Commits:** 5

---

## Prevention Checklist

For future deployments and similar issues:

**Code Quality:**
- [ ] Create base configuration class for common fields
- [ ] Add unit tests for load_existing_configuration() with all cloud providers
- [ ] Validate config object has all required attributes before use
- [ ] Add type hints and runtime validation

**Multi-Cloud Support:**
- [ ] Document cloud-specific differences (security models, resource names, etc.)
- [ ] Implement cloud-specific fallback logic
- [ ] Add explicit kubectl context management
- [ ] Test skip-terraform mode on all cloud providers

**GKE-Specific:**
- [ ] Document system pod resource overhead
- [ ] Provide node sizing guidance (minimum e2-medium)
- [ ] Set lower default resource requests for GKE
- [ ] Add GKE cluster autoscaling configuration

**Testing:**
- [ ] Test skip-terraform mode end-to-end
- [ ] Test with multiple kubectl contexts configured
- [ ] Test with minimal node sizes
- [ ] Test encryption key fallback logic

**Documentation:**
- [ ] Add troubleshooting guide for context switching
- [ ] Document GCP Secret Manager vs Terraform outputs
- [ ] Add kubectl context verification commands
- [ ] Document minimum node requirements per cloud

---

## Related Documentation

- [gcp-lessons-learned.md](./gcp-lessons-learned.md) - Initial GCP deployment (gke-gcloud-auth-plugin issue)
- [gcp-requirements.md](./gcp-requirements.md) - GCP prerequisites and setup
- [terraform/gcp/README.md](../../terraform/gcp/README.md) - GCP Terraform module documentation

---

## Commits

- e79c331 - fix: load correct config class in load_existing_configuration for GCP/Azure
- 7fcaca5 - fix: add fallback for encryption key from config in skip-terraform mode
- ec45cb9 - fix: add missing timezone and persistence_size to GCPDeploymentConfig
- 2f41c8c - fix: add kubectl context verification and switching for multi-cloud deployments
- 3151e63 - fix: add missing tls_certificate_source attribute to GCPDeploymentConfig

---

*Documented by: Claude Code*
*Date: October 28, 2025*
*GCP Project: cross-cloud-475812*
*GKE Cluster: n8n-gke-cluster (us-central1)*
*LoadBalancer IP: 136.114.23.83*
