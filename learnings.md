# Deployment Learnings: N8N on AWS EKS

## Overview
This document captures critical learnings from deploying n8n on AWS EKS, specifically addressing AWS Elastic IP (EIP) limits, EKS cluster requirements, and Terraform state management challenges.

---

## Problem Summary

### Initial Issue
Terraform deployment failed with two critical errors:
1. **EIP Limit Exceeded**: "The maximum number of addresses has been reached" (5/5 limit)
2. **Node Group Creation Failed**: "Instances failed to join the kubernetes cluster"

### Timeline
- Infrastructure partially created (VPC, EKS cluster, RDS)
- Failed at: NAT Gateway EIP allocation and Node Group creation
- Duration to resolution: ~2 hours

---

## Root Cause Analysis

### 1. AWS EIP Limits
**Default Limit**: 5 Elastic IPs per region per account

**Actual Usage**:
- Existing EIPs: 2 (other VPCs)
- New deployment attempt: 4 (3 for NLB + 1 for NAT Gateway)
- **Total**: 6 (exceeded limit by 1)

**Why This Happened**:
- Original configuration assumed `length(local.azs)` EIPs for NLB
- Configuration used 3 AZs, requiring 3 NLB EIPs
- NAT Gateway needed 1 additional EIP
- No EIP limit check in initial design

### 2. Node Group Failure
**Root Cause**: Cascading failure from NAT Gateway creation failure

**Technical Details**:
- EKS nodes are deployed in **private subnets**
- Private subnets require **NAT Gateway** for internet access
- Nodes need internet access to:
  - Download container images from ECR
  - Join the EKS cluster control plane
  - Install add-ons (EBS CSI driver, etc.)
- Without NAT Gateway → No internet → Node registration fails

### 3. EKS Cluster AZ Immutability
**Critical Discovery**: EKS clusters **cannot change their AZ configuration** after creation

**What We Learned**:
```
EKS Cluster created with AZs: [us-west-2a, us-west-2b, us-west-2c]
↓
Cannot later change to: [us-west-2a, us-west-2b]
```

**Error Message**:
```
InvalidParameterException: Provided subnets belong to the AZs 'us-west-2a,us-west-2b'.
But they should belong to the exact set of AZs 'us-west-2a,us-west-2b,us-west-2c'
in which subnets were provided during cluster creation.
```

---

## Solution Implemented

### Architecture Decision
**Strategy**: Decouple NLB EIP count from AZ count

**Configuration**:
```hcl
locals {
  azs               = slice(..., 0, min(3, ...))  # 3 AZs for EKS
  nat_gateway_count = 1                            # 1 NAT Gateway
  nlb_eip_count     = 2                            # 2 NLB EIPs (not 3!)
}
```

**Why This Works**:
- EKS requires all 3 original AZs ✓
- NLB can function with 2 EIPs across 2 AZs ✓
- NAT Gateway provides internet for all 3 private subnets ✓
- Total EIPs: 2 (NLB) + 1 (NAT) + 2 (existing) = 5 ✓

### Implementation Steps

#### 1. Free Up EIP Capacity
```bash
# Released unassociated NLB EIP
aws ec2 release-address --allocation-id eipalloc-0cdf05cf986139779 --region us-west-2
```

#### 2. Clean Terraform State
```bash
# Remove failed resources
terraform state rm aws_eks_node_group.main
terraform state rm 'aws_eip.nlb[2]'
terraform state rm 'aws_subnet.public[2]'
terraform state rm 'aws_subnet.private[2]'
terraform state rm 'aws_route_table_association.public[2]'
```

#### 3. Restore Deleted Resources
```bash
# Import third AZ subnets back (EKS requirement)
terraform import 'aws_subnet.public[2]' subnet-0cff955627a665fbb
terraform import 'aws_subnet.private[2]' subnet-04320f7eec7b4035a
terraform import 'aws_route_table_association.public[2]' subnet-0cff955627a665fbb/rtb-...
```

#### 4. Delete Failed Node Group
```bash
# Node group in CREATE_FAILED state blocked new creation
aws eks delete-nodegroup \
  --cluster-name n8n-eks-cluster \
  --nodegroup-name n8n-app-node-group \
  --region us-west-2
```

#### 5. Modified Terraform Configuration
```hcl
# Main changes in main.tf

# 1. Added NLB EIP count control
locals {
  nlb_eip_count = 2  # Separate from AZ count
}

# 2. Updated EIP resource
resource "aws_eip" "nlb" {
  count = var.enable_nginx_ingress ? local.nlb_eip_count : 0
  # ... rest of config
}

# 3. Updated Helm values to use only 2 EIPs
values = [
  templatefile("${path.module}/nginx-ingress-values.tpl", {
    nlb_eips    = join(",", slice(aws_eip.nlb[*].id, 0, local.nlb_eip_count))
    nlb_subnets = join(",", slice(aws_subnet.public[*].id, 0, local.nlb_eip_count))
  })
]
```

---

## Key Technical Learnings

### 1. AWS EIP Management

**Lesson**: Always check and plan for EIP limits before deployment

**Best Practices**:
- Audit existing EIPs before deployment:
  ```bash
  aws ec2 describe-addresses --region <region> --query 'length(Addresses)'
  ```
- Design with EIP efficiency:
  - Use 1 NAT Gateway instead of 3 (cross-AZ cost vs. EIP limit)
  - Share EIPs where possible
  - Consider AWS NAT instances or egress-only gateways
- Request limit increases proactively for production

**EIP Usage Patterns**:
```
Cost-Optimized (Low EIP usage):
- 1 NAT Gateway (1 EIP)
- 2 NLB EIPs
- Total: 3 EIPs

High-Availability (High EIP usage):
- 3 NAT Gateways (3 EIPs)
- 3 NLB EIPs
- Total: 6 EIPs (requires limit increase!)
```

### 2. EKS Cluster Constraints

**Immutable Properties**:
- ✗ Cannot change AZ configuration after creation
- ✗ Cannot reduce number of AZs
- ✗ Cannot change subnet assignments

**What You CAN Change**:
- ✓ Node group configuration
- ✓ Add/remove node groups
- ✓ Modify security groups
- ✓ Update IAM roles

**Implication for Infrastructure as Code**:
- Test AZ decisions thoroughly before first apply
- Use consistent AZ strategy across environments
- Document AZ requirements in code comments

### 3. Terraform State Management

**Critical Operations Performed**:
1. **State Removal**: Remove failed/incorrect resources
2. **State Import**: Re-import existing AWS resources
3. **Partial Apply**: Apply changes incrementally

**State Management Best Practices**:
```bash
# Always backup state before manipulation
cp terraform.tfstate terraform.tfstate.backup

# Remove resources safely
terraform state rm 'resource.name[index]'

# Import existing resources
terraform import 'resource.name[index]' <aws-resource-id>

# Verify state
terraform state list | grep <pattern>
```

**When State Gets Out of Sync**:
1. Configuration restore doesn't lose state (`.tfstate` is separate from `.tf`)
2. Use `terraform state show` to inspect resources
3. Manual AWS operations require state updates
4. Failed resources must be removed from state before retry

### 4. EKS Networking Architecture

**Why Private Subnets + NAT Gateway**:
- **Security**: Nodes don't have public IPs
- **Access Control**: All egress traffic through NAT
- **Best Practice**: Production workloads should be in private subnets

**Internet Connectivity Flow**:
```
EKS Node (Private Subnet)
  ↓
Private Route Table → NAT Gateway
  ↓
Internet Gateway
  ↓
Internet (ECR, EKS API, etc.)
```

**Without NAT Gateway**:
- ✗ Cannot pull container images
- ✗ Cannot register with cluster
- ✗ Cannot download kubectl/kubelet
- Result: `NodeCreationFailure`

### 5. NLB and Static IPs

**Why NLB Uses EIPs**:
- Provides static, predictable IP addresses
- Required for DNS A record configuration
- Enables firewall whitelisting

**NLB EIP Configuration**:
```hcl
# Kubernetes Service annotation
service.beta.kubernetes.io/aws-load-balancer-eip-allocations: "eip1,eip2"
service.beta.kubernetes.io/aws-load-balancer-subnets: "subnet1,subnet2"
```

**Key Insight**: NLB can function with fewer EIPs than AZs
- 2 EIPs across 2 AZs is valid
- Traffic still distributed, slightly reduced HA
- Cost/complexity trade-off

---

## Troubleshooting Techniques Used

### 1. Error Analysis
```bash
# Check EIP usage
aws ec2 describe-addresses --region us-west-2

# Verify cluster state
aws eks describe-cluster --name n8n-eks-cluster --region us-west-2

# Check node group status
aws eks describe-nodegroup --cluster-name ... --nodegroup-name ...

# Inspect failed instances
aws ec2 describe-instances --filters "Name=tag:eks:nodegroup-name,Values=..."
```

### 2. State Inspection
```bash
# Count resources in state
terraform show -json | jq '.values.root_module.resources | length'

# List specific resources
terraform state list | grep -E "(nat|eip|node)"

# Show resource details
terraform state show aws_eks_node_group.main
```

### 3. Incremental Recovery
1. Identify minimum viable changes
2. Remove blocking resources
3. Import necessary resources
4. Apply in controlled steps
5. Verify each step before proceeding

### 4. AWS Resource Cleanup
```bash
# Wait for deletion completion
while true; do
  status=$(aws eks describe-nodegroup ... 2>&1)
  if echo "$status" | grep -q "ResourceNotFoundException"; then
    break
  fi
  sleep 10
done
```

---

## Cost Optimization Insights

### NAT Gateway Strategy

**Option 1: Single NAT Gateway (Implemented)**
- Cost: ~$32/month (1 NAT Gateway)
- EIPs: 1
- Risk: Single point of failure
- Best for: Development, staging

**Option 2: Multi-AZ NAT Gateways**
- Cost: ~$96/month (3 NAT Gateways)
- EIPs: 3
- Risk: None (HA)
- Best for: Production

**Cross-AZ Data Transfer**:
- $0.01/GB between AZs
- Estimate: ~$5-20/month depending on traffic
- Single NAT Gateway incurs this cost; multi-AZ NAT avoids it

### NLB EIP Count Trade-offs

| EIPs | Coverage | Cost/Month | HA Level | EIP Limit Impact |
|------|----------|------------|----------|------------------|
| 1    | 1 AZ     | $3.60      | Low      | Low              |
| 2    | 2 AZs    | $7.20      | Medium   | Medium           |
| 3    | 3 AZs    | $10.80     | High     | High             |

**Decision Matrix**:
- Development: 1-2 EIPs
- Production: 2-3 EIPs (or request limit increase)

---

## Setup.py Integration Learnings

### Skip-Terraform Mode

**Discovery**: `setup.py` has built-in support for manual Terraform runs

**Usage**:
```bash
# After manual terraform apply
python3 setup.py --skip-terraform
```

**What It Does**:
1. Loads configuration from `terraform.tfvars`
2. Reads outputs from `terraform.tfstate`
3. Configures kubectl for the cluster
4. Deploys application using Helm
5. Waits for LoadBalancer readiness

**Key Insight**: Separating infrastructure (Terraform) from application (Helm) provides:
- Better error recovery
- Incremental deployment capability
- Clearer separation of concerns

---

## Prevention Strategies

### 1. Pre-deployment Checklist
```bash
#!/bin/bash
# AWS Deployment Pre-flight Check

# Check EIP availability
CURRENT_EIPS=$(aws ec2 describe-addresses --region $REGION --query 'length(Addresses)' --output text)
NEEDED_EIPS=3
AVAILABLE=$((5 - CURRENT_EIPS))

if [ $AVAILABLE -lt $NEEDED_EIPS ]; then
  echo "ERROR: Insufficient EIP capacity"
  echo "Current: $CURRENT_EIPS/5, Need: $NEEDED_EIPS, Available: $AVAILABLE"
  exit 1
fi

# Check AWS credentials
aws sts get-caller-identity || exit 1

# Verify region supports 3+ AZs
AZ_COUNT=$(aws ec2 describe-availability-zones --region $REGION --query 'length(AvailabilityZones)' --output text)
if [ $AZ_COUNT -lt 3 ]; then
  echo "ERROR: Region has only $AZ_COUNT AZs (need 3)"
  exit 1
fi

echo "✓ Pre-flight checks passed"
```

### 2. Terraform Validation
```hcl
# Add validation rules to variables.tf

variable "enable_multi_nat" {
  type        = bool
  default     = false
  description = "Enable NAT Gateway in each AZ (requires more EIPs)"

  validation {
    condition     = !var.enable_multi_nat || var.enable_multi_nat == false
    error_message = "Multi-NAT requires additional EIPs. Ensure limit allows: azs * 2 EIPs"
  }
}
```

### 3. Documentation
- Document EIP requirements in `README.md`
- Add comments in `main.tf` explaining EIP allocations
- Include troubleshooting guide for common issues

---

## Production Recommendations

### 1. EIP Limit Management
- **Request increase** to 15 EIPs for production accounts
- Use separate AWS accounts per environment (dev/staging/prod)
- Monitor EIP usage with CloudWatch/AWS Config

### 2. High Availability
- Use 3 NAT Gateways in production (one per AZ)
- Use 3 NLB EIPs for full multi-AZ coverage
- Configure proper health checks

### 3. State Management
- Use S3 backend with state locking:
  ```hcl
  terraform {
    backend "s3" {
      bucket         = "terraform-state-bucket"
      key            = "n8n/terraform.tfstate"
      region         = "us-west-2"
      encrypt        = true
      dynamodb_table = "terraform-locks"
    }
  }
  ```
- Enable state versioning
- Implement automated backups

### 4. Deployment Strategy
```
1. terraform plan -out=plan.tfplan
2. Review plan carefully (especially EIP allocations)
3. terraform apply plan.tfplan
4. On failure: Document state, clean up, retry with fixes
5. Use --skip-terraform for application redeployments
```

---

## Lessons for Similar Deployments

### 1. AWS Service Limits
- **Always check** service limits before deployment
- Common limits to verify:
  - EIPs (5 per region)
  - VPCs (5 per region)
  - NAT Gateways (no hard limit but cost consideration)
  - EKS clusters (no hard limit)
  - EC2 instances (varies by instance type)

### 2. EKS Best Practices
- Design AZ strategy upfront (immutable after creation)
- Use private subnets for nodes
- Always provision NAT Gateway for private subnets
- Plan for multi-AZ from day one (even if starting with 1-2)

### 3. Terraform Workflow
- Test with `terraform plan` thoroughly
- Apply incrementally in new environments
- Keep state backups
- Document manual interventions
- Use modules for reusable patterns

### 4. Error Recovery
- Don't panic—state can be recovered
- Understand resource dependencies (NAT → Nodes → Apps)
- Clean up failed resources before retry
- AWS resources can be imported back into Terraform

---

## Conclusion

This deployment taught us valuable lessons about:
1. **AWS Limits**: EIP constraints are real and must be planned for
2. **EKS Immutability**: Cluster AZ configuration cannot be changed
3. **State Management**: Terraform state is resilient but requires care
4. **Architecture Decisions**: Trade-offs between HA, cost, and limits

**Key Takeaway**: Infrastructure design must account for cloud provider limits and service constraints from the start. What seems like a minor configuration detail (number of AZs) can have cascading implications on resource allocation and deployment success.

---

## References

- [AWS EIP Limits](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html#using-instance-addressing-limit)
- [EKS Cluster Networking](https://docs.aws.amazon.com/eks/latest/userguide/network_reqs.html)
- [Terraform State Management](https://developer.hashicorp.com/terraform/language/state)
- [AWS NAT Gateway Pricing](https://aws.amazon.com/vpc/pricing/)

---

**Date**: 2025-10-17
**Environment**: us-west-2
**Deployment**: n8n on EKS with RDS PostgreSQL
**Status**: ✓ Successfully Resolved and Deployed
