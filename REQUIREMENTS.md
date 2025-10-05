# N8N AWS Deployment Automation - Requirements Document

**Version**: 1.0
**Date**: 2025-10-05
**Status**: Draft

---

## 1. Executive Summary

This document defines the requirements for an automated deployment system that simplifies the provisioning and configuration of n8n (workflow automation platform) on AWS EKS (Kubernetes).

**Project Name**: N8N EKS Deployment CLI
**Target Platform**: Amazon Web Services EKS (Elastic Kubernetes Service)
**Deployment Target**: n8n Workflow Automation Platform
**Primary Deliverable**: Interactive CLI application with Infrastructure-as-Code automation (Terraform + Helm)

---

## 2. Problem Statement

### 2.1 Current State

Deploying n8n on AWS EKS currently requires:
- Manual infrastructure provisioning (VPC, EKS clusters, node groups, networking)
- Deep knowledge of Terraform and Kubernetes/Helm
- Understanding of AWS networking, security, IAM, and IRSA
- Manual configuration of n8n encryption keys, domains, and environment variables
- Error-prone manual editing of infrastructure configuration files
- Complex troubleshooting when deployments fail
- Time-consuming setup (3-5 hours for experienced users, 2+ days for beginners)

### 2.2 Business Impact

**For Individual Users/Small Teams:**
- High barrier to entry for self-hosting n8n
- Risk of misconfiguration leading to security vulnerabilities
- Wasted time on infrastructure instead of building workflows
- Difficulty reproducing deployments across environments

**For Organizations:**
- Inconsistent deployment practices across teams
- Lack of deployment standardization
- Higher total cost of ownership due to manual processes
- Compliance and security risks from ad-hoc configurations

### 2.3 Desired Future State

A single command (`python3 setup.py`) should:
1. Guide users through deployment decisions with clear prompts
2. Validate prerequisites and surface issues early
3. Automatically provision secure, production-ready infrastructure
4. Deploy n8n with minimal user input
5. Provide clear post-deployment instructions
6. Enable easy cleanup and teardown

---

## 3. Goals and Objectives

### 3.1 Primary Goals

1. **Reduce deployment time** from hours to 25-30 minutes
2. **Lower expertise barrier** so developers without deep EKS/K8s knowledge can deploy
3. **Eliminate configuration errors** through validation and automation
4. **Enable consistent deployments** across development, staging, and production
5. **Maintain security best practices** by default (multi-AZ, encryption, private subnets)

### 3.2 Success Metrics

- Users can deploy n8n on EKS in < 30 minutes (vs 3-5 hours manual)
- 90% of users successfully deploy on first attempt
- Zero manual file editing required for standard deployments
- All deployments follow AWS security best practices (encryption, private subnets, least privilege IAM)
- Production-ready infrastructure with high availability out of the box

### 3.3 Non-Goals

The following are explicitly **out of scope**:
- Multi-cloud support (Azure, GCP) - AWS only
- Database migration tools
- n8n workflow development/editing
- Custom application code deployment
- Monitoring/observability stack deployment (users can add later)
- CI/CD pipeline integration (this is a bootstrap tool)

---

## 4. User Personas

### 4.1 Primary Persona: DevOps Engineer

**Name**: Marcus
**Role**: Senior DevOps Engineer
**Experience**: Expert with AWS, Kubernetes, Terraform
**Goals**:
- Deploy production-grade n8n for company
- Scalable, highly available setup
- Infrastructure as code for version control
- Multi-AZ deployment for reliability

**Needs**:
- Production-ready EKS deployment
- Ability to customize infrastructure (instance types, resources)
- Terraform modules that can be audited
- High availability and fault tolerance

**Pain Points**:
- Wants to avoid writing boilerplate Terraform
- Needs to ensure compliance with company policies
- Must document deployment for team
- Requires reproducible infrastructure

### 4.2 Secondary Persona: Startup Technical Lead

**Name**: Raj
**Role**: CTO of 10-person startup
**Experience**: Strong development, moderate DevOps
**Goals**:
- Deploy n8n for team automation workflows
- Production-ready but cost-conscious
- Quick initial setup with room to scale
- Minimal ongoing maintenance

**Needs**:
- Single command deployment
- Clear cost estimates upfront
- Idempotent deployments (can re-run safely)
- Room to grow (scaling, additional environments)

**Pain Points**:
- Limited DevOps bandwidth
- Budget constraints but need reliability
- Needs production-ready setup without manual tuning
- Needs to move fast

---

## 5. Functional Requirements

### 5.1 Core Functionality

#### FR-1: Interactive CLI Application

**Priority**: MUST HAVE
**User Story**: As a user, I want an interactive CLI that guides me through EKS deployment so I don't have to read extensive documentation.

**Requirements**:
- Single entry point: `python3 setup.py`
- Color-coded output for status (success, warning, error, info)
- Clear prompts with default values shown
- Ability to interrupt and resume (Ctrl+C handling)
- Progress indicators for long-running operations
- Summary of configuration before applying changes

**Acceptance Criteria**:
- Script runs on Linux/macOS with Python 3.7+
- All prompts have clear descriptions
- User can exit cleanly at any point without corrupting state
- Configuration summary shows all values before deployment

---

#### FR-2: Dependency Validation

**Priority**: MUST HAVE
**User Story**: As a user, I want the tool to check for required dependencies upfront so I don't encounter errors mid-deployment.

**Requirements**:
- Check for required tools:
  - Terraform (>= 1.6)
  - AWS CLI (>= 2.0)
  - Python 3 (>= 3.7)
  - Helm (>= 3.0)
  - kubectl
- Provide installation instructions for missing tools
- Exit gracefully if critical dependencies missing

**Acceptance Criteria**:
- All dependency checks run before prompting for configuration
- Clear indication of which tools are installed vs missing
- Installation URLs provided for missing dependencies
- Script exits with helpful message if dependencies not met

---

#### FR-3: AWS Authentication & Profile Management

**Priority**: MUST HAVE
**User Story**: As a user, I want the tool to use my existing AWS profiles and validate credentials before attempting deployment.

**Requirements**:
- Auto-detect available AWS CLI profiles
- Display profiles as numbered list for selection
- Allow manual profile name entry
- Validate credentials using `aws sts get-caller-identity`
- Test credentials can access selected region
- Show AWS account ID and identity being used

**Acceptance Criteria**:
- Lists all configured AWS profiles from `~/.aws/config`
- Selected profile tested before proceeding
- Clear error message if authentication fails
- User informed which AWS account/region will be used

---

#### FR-4: Configuration Prompts

**Priority**: MUST HAVE
**User Story**: As a user, I want to be prompted for all necessary configuration so the deployment is customized to my needs.

**Requirements**:

**EKS Configuration:**
- AWS Region (with list of options)
- EKS cluster name (default provided)
- Node instance types (t3.small, t3.medium, t3.large)
- Node group sizing (min/desired/max)
- Kubernetes namespace (default: n8n)
- Storage size for PVC (default: 10Gi)
- Timezone for n8n (default: America/Bahia)
- n8n encryption key (generate new or provide existing)

**TLS/Certificate Configuration:**
- Prompt: "Configure TLS/HTTPS?" [Y/n] (default: n)
- If NO: Deploy with HTTP only, show NLB DNS/IP for access
- If YES:
  - Prompt for domain name (FQDN) - required for TLS
  - Prompt: "Certificate source?"
    - Option 1: "Bring your own certificate"
      - Prompt for certificate file path (PEM format)
      - Prompt for private key file path (PEM format)
      - Validate certificate and key match
      - Validate certificate expiration date
    - Option 2: "Auto-generate via Let's Encrypt (HTTP-01 validation)"
      - Prompt for email address for Let's Encrypt notifications
      - Deploy cert-manager to cluster
      - Create ClusterIssuer for Let's Encrypt
      - Warn user to configure DNS before validation
      - Show DNS configuration instructions
    - Option 3: "Configure later"
      - Deploy without TLS initially
      - Provide instructions for running `setup.py --update-tls` later

**Acceptance Criteria**:
- All required values prompted with clear descriptions
- Default values shown in prompts
- Input validation:
  - Encryption key must be 64 hex chars
  - Domain must be valid FQDN format
  - Certificate file must be readable and valid PEM
  - Private key file must be readable and valid PEM
  - Certificate and private key must match
  - Email must be valid format (for Let's Encrypt)
- Optional fields clearly marked as optional
- TLS configuration can be skipped entirely
- User can choose to configure TLS later

---

#### FR-5: Idempotent Operations

**Priority**: MUST HAVE
**User Story**: As a user, I want to be able to interrupt the setup and re-run it without corrupting my configuration.

**Requirements**:
- No changes applied until user confirms configuration summary
- Create backups of all files before modification
- Automatic restore of backups if interrupted (Ctrl+C)
- Safe to re-run setup multiple times
- Terraform state managed properly (no duplicate resources)

**Acceptance Criteria**:
- Configuration files only modified after confirmation
- Backup files created for: variables.tf, values.yaml, terraform.tfvars
- Signal handlers catch Ctrl+C and restore backups
- Multiple runs don't create duplicate resources

---

#### FR-6: Encryption Key Management

**Priority**: MUST HAVE
**User Story**: As a user, I need secure encryption key generation and storage for n8n.

**Requirements**:
- Offer to auto-generate 64-character hex encryption key
- Allow user to provide existing key
- Validate key format (64 hex characters)
- Store key in AWS SSM Parameter Store (SecureString)
- Display key to user once (they must save it)
- Never log key in plaintext

**Acceptance Criteria**:
- Generated keys are cryptographically secure (use `secrets` module)
- Keys stored in SSM with encryption
- User warned to save key securely
- Key never appears in Terraform state in plaintext

---

#### FR-7: TLS/Certificate Management

**Priority**: MUST HAVE
**User Story**: As a user, I want flexible TLS configuration options during initial deployment and the ability to update certificates later.

**Requirements**:

**Initial Deployment Options:**

1. **Option 1: No TLS (Public IP only)**
   - Deploy with Network Load Balancer and public IP
   - Access n8n via `http://<load-balancer-dns>` or `http://<elastic-ip>`
   - No domain required
   - No certificate configuration
   - HTTPS disabled on ingress

2. **Option 2: TLS with Domain (Bring Your Own Certificate)**
   - User provides domain name (FQDN)
   - User provides TLS certificate and private key (PEM format)
   - Setup validates certificate format
   - Certificate stored as Kubernetes Secret
   - Ingress configured with TLS enabled
   - Access n8n via `https://<your-domain>`

3. **Option 3: TLS with Domain (Auto-generated via Let's Encrypt)**
   - User provides domain name (FQDN)
   - Setup deploys cert-manager to cluster
   - Setup creates ClusterIssuer for Let's Encrypt (HTTP-01 validation)
   - Certificate automatically requested and validated
   - Certificate auto-renewed before expiration
   - Ingress configured with TLS enabled and cert-manager annotations
   - Access n8n via `https://<your-domain>`

**Post-Deployment Certificate Updates:**

The tool must support updating TLS configuration after initial deployment:

1. **Add TLS to existing non-TLS deployment**
   - Re-run setup.py with `--update-tls` flag
   - Prompt for domain and certificate option
   - Update ingress configuration
   - No downtime required (rolling update)

2. **Update existing certificates (BYO)**
   - Re-run setup.py with `--update-tls` flag
   - Provide new certificate and private key
   - Update Kubernetes Secret
   - Ingress automatically picks up new certificate
   - No pod restart required

3. **Switch from BYO to Let's Encrypt (or vice versa)**
   - Re-run setup.py with `--update-tls` flag
   - Select new certificate option
   - Update ingress annotations and secrets
   - Minimal downtime during certificate switch

**Technical Implementation:**

- **Elastic IP Allocation**: NLB created with static Elastic IP for consistent DNS mapping
- **Cert-Manager Integration**: Deploy cert-manager v1.13+ via Helm (if auto-generation selected)
- **ClusterIssuer Configuration**: HTTP-01 challenge via ingress
- **Certificate Storage**: Kubernetes TLS secrets in n8n namespace
- **Ingress TLS Configuration**:
  - `tls.enabled: true/false` based on user choice
  - `tls.secretName` pointing to certificate secret
  - cert-manager annotations if using Let's Encrypt
- **DNS Validation**: Warn user that DNS must point to NLB IP before Let's Encrypt validation
- **Certificate Monitoring**: Use cert-manager's auto-renewal (30 days before expiration)

**Acceptance Criteria**:

**Initial Deployment:**
- [ ] User can deploy without domain/TLS (Option 1)
- [ ] User can deploy with BYO certificates (Option 2)
- [ ] User can deploy with Let's Encrypt auto-generation (Option 3)
- [ ] Certificate validation catches invalid PEM format
- [ ] Let's Encrypt HTTP-01 challenge completes successfully
- [ ] Ingress serves traffic over HTTPS when TLS enabled
- [ ] Access via HTTP redirects to HTTPS when TLS enabled

**Certificate Updates:**
- [ ] User can add TLS to existing non-TLS deployment
- [ ] User can update BYO certificates without downtime
- [ ] User can switch between BYO and Let's Encrypt
- [ ] Certificate updates don't require pod restarts
- [ ] Old certificates are backed up before replacement

**Error Handling:**
- [ ] Invalid certificate format rejected with clear error
- [ ] Certificate/key mismatch detected
- [ ] Domain validation (valid FQDN format)
- [ ] DNS not pointing to NLB shows warning (for Let's Encrypt)
- [ ] Let's Encrypt rate limit errors handled gracefully

**Security:**
- [ ] Private keys never logged or displayed
- [ ] Certificates stored in Kubernetes Secrets (encrypted at rest)
- [ ] TLS 1.2+ enforced
- [ ] Strong cipher suites configured

---

#### FR-8: Infrastructure Provisioning

**Priority**: MUST HAVE
**User Story**: As a user, I want the tool to automatically provision all required AWS EKS infrastructure.

**Requirements**:

**Must Create:**
- VPC with public/private subnets across 3 AZs
- NAT Gateways for private subnet internet access
- Internet Gateway for public subnet access
- Route tables for public and private subnets
- EKS cluster (version 1.31)
- Node group in private subnets
- EBS CSI driver addon
- Default StorageClass for EBS volumes (gp3)
- IAM roles for cluster and nodes (IRSA for EBS CSI)
- SSM Parameter for encryption key (SecureString)
- NGINX Ingress Controller with Network Load Balancer
- Static Elastic IP for NLB (for consistent DNS mapping)
- n8n Helm release with proper configuration

**Conditionally Create (based on TLS configuration):**
- cert-manager (v1.13+) via Helm - if user selects Let's Encrypt option
- ClusterIssuer for Let's Encrypt (HTTP-01 challenge) - if using Let's Encrypt
- Kubernetes TLS Secret - if user provides BYO certificates
- Ingress TLS configuration - if TLS enabled

**Acceptance Criteria**:
- All resources tagged appropriately
- Infrastructure follows AWS best practices
- Private subnets used for compute workloads (nodes)
- Encryption enabled where applicable (EBS, SSM)
- Least privilege IAM policies
- Multi-AZ deployment for high availability
- NLB has static Elastic IP allocated
- cert-manager only deployed if Let's Encrypt selected
- TLS configuration applied correctly based on user choice

---

#### FR-9: Terraform Execution

**Priority**: MUST HAVE
**User Story**: As a user, I want the tool to run Terraform commands automatically and show me the results.

**Requirements**:
- Run `terraform init` in terraform directory
- Generate `terraform.tfvars` with user configuration
- Run `terraform plan` and show summary
- Prompt user to confirm plan
- Run `terraform apply` with auto-approve after confirmation
- Stream Terraform output in real-time
- Handle Terraform errors gracefully
- Display Terraform outputs after successful apply

**Acceptance Criteria**:
- Terraform commands executed in correct order
- User sees real-time progress
- Errors caught and displayed clearly
- Outputs extracted and formatted for user
- terraform.tfvars contains all user-provided values

---

#### FR-10: Helm Deployment

**Priority**: MUST HAVE
**User Story**: As a user, I want n8n automatically deployed to Kubernetes after cluster creation.

**Requirements**:
- Update helm/values.yaml with user configuration
- Configure kubectl context for new cluster
- Run `helm install n8n ./helm`
- Wait for deployment to be ready
- Verify pods are running
- Display ingress URL to user

**Acceptance Criteria**:
- Helm chart installs successfully
- n8n pod reaches Running state
- PVC bound to storage
- Ingress created with correct hostname
- User given kubectl commands for verification

---

#### FR-11: Post-Deployment Information

**Priority**: MUST HAVE
**User Story**: As a user, I want clear instructions on how to access my n8n instance after deployment.

**Requirements**:
- Display n8n access URL (ingress hostname)
- Show relevant resource identifiers (cluster name, cluster endpoint, VPC ID)
- Provide next steps (DNS configuration for ingress hostname)
- Show kubectl commands to check status
- Display commands for viewing logs
- Show cleanup/teardown instructions (terraform destroy)

**Acceptance Criteria**:
- Ingress URL displayed prominently
- All Terraform outputs formatted clearly
- DNS configuration steps explained
- kubectl command examples provided for monitoring
- Cleanup instructions clear and safe

---

#### FR-12: Error Handling & Recovery

**Priority**: SHOULD HAVE
**User Story**: As a user, I want clear error messages and recovery instructions when something goes wrong.

**Requirements**:
- Catch common errors (auth failures, quota limits, invalid input)
- Display actionable error messages
- Suggest fixes for known issues
- Restore backups on failure
- Provide commands to manually complete deployment
- Log errors for debugging

**Acceptance Criteria**:
- No Python stack traces shown to user (except in debug mode)
- Error messages explain what went wrong
- Suggestions provided for remediation
- Backups restored automatically on failure

---

### 5.2 Configuration Management

#### FR-13: File Modification Strategy

**Priority**: MUST HAVE
**User Story**: As a maintainer, I need the tool to modify configuration files in a safe, version-control-friendly way.

**Requirements**:
- **DO**: Modify terraform.tfvars (this is user config)
- **DO**: Create custom values files for Helm
- **DO NOT**: Modify variables.tf (this is source code)
- **DO NOT**: Modify values.yaml directly (this is template)
- Use Helm `--set` or `--values` for overrides
- Keep source files clean for git

**Acceptance Criteria**:
- No version-controlled files modified (except terraform.tfvars)
- Git status clean after deployment (except tfvars)
- Configuration changes isolated to user config files

---

### 5.3 Security Requirements

#### FR-14: Security Best Practices

**Priority**: MUST HAVE
**User Story**: As a user, I want my deployment to follow security best practices without extra effort.

**Requirements**:
- Private subnets for all compute resources (EKS nodes)
- Encryption at rest (EBS volumes, SSM parameters)
- Encryption in transit (HTTPS/TLS for ingress)
- Least privilege IAM roles (IRSA for EBS CSI driver)
- Security groups with minimal required ports
- No hardcoded credentials in code
- Secrets stored in SSM Parameter Store (SecureString)
- Multi-AZ deployment for high availability

**Acceptance Criteria**:
- All EKS nodes in private subnets
- EBS volumes encrypted (default StorageClass with encryption enabled)
- SSM parameters use SecureString type
- IAM policies follow least privilege principle
- IRSA configured for EBS CSI driver
- No credentials in git repository or Terraform state (plaintext)

---

## 6. Non-Functional Requirements

### 6.1 Performance

**NFR-1: Deployment Time**
- EKS deployment: Complete in < 30 minutes (cluster creation is ~15-20 minutes)
- Dependency checks: Complete in < 10 seconds
- AWS authentication: Complete in < 5 seconds
- Configuration prompts: Complete in < 5 minutes

**NFR-2: Resource Efficiency**
- CLI tool: < 100MB memory usage
- No unnecessary API calls to AWS
- Terraform state handled efficiently
- Streaming output for long-running operations

---

### 6.2 Usability

**NFR-3: User Experience**
- All prompts use plain language (avoid jargon)
- Progress indicators for operations > 10 seconds
- Color coding for different message types
- Clear structure: validation → configuration → deployment → completion
- No more than 15 prompts for standard deployment

**NFR-4: Documentation**
- README with quick start (< 5 minute read)
- Inline help text for all prompts
- Troubleshooting guide for common issues
- Example configurations provided

---

### 6.3 Reliability

**NFR-5: Error Recovery**
- Graceful handling of network interruptions
- Automatic retry for transient failures (with backoff)
- State rollback on critical failures
- No partial deployments (all or nothing)

**NFR-6: Idempotency**
- Running setup multiple times produces same result
- No duplicate resources created
- Safe to re-run after interruption

---

### 6.4 Maintainability

**NFR-7: Code Quality**
- Python code follows PEP 8 style guide
- Terraform code follows HashiCorp best practices
- Helm charts follow Kubernetes conventions
- Modular design (separate classes for concerns)
- Type hints in Python code
- Comments for complex logic

**NFR-8: Testability**
- Dependency checking unit testable
- Configuration validation unit testable
- AWS operations mockable
- Terraform plans reviewable without apply

---

### 6.5 Portability

**NFR-9: Platform Support**
- Works on Linux (Ubuntu 20.04+, Amazon Linux 2)
- Works on macOS (11.0+)
- Python 3.7+ compatibility
- No OS-specific dependencies beyond Python standard library

---

### 6.6 Cost Optimization

**NFR-10: Cost Awareness**
- Display estimated monthly costs before deployment
- Default to cost-effective instance types (t3.medium for nodes)
- Warn about expensive resources (NAT Gateways, Load Balancers, EKS control plane)
- Provide cost optimization recommendations
- Explain cost breakdown clearly

**Cost Target:**
- EKS deployment: $150-260/month (control plane ~$73 + nodes ~$60 + NAT gateways ~$97 + NLB ~$16)

---

## 7. System Architecture

### 7.1 Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        USER                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ python3 setup.py
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   SETUP CLI (Python)                        │
│  ┌──────────────┬────────────────┬──────────────────────┐  │
│  │  Dependency  │  Config        │  AWS Auth            │  │
│  │  Checker     │  Collector     │  Validator           │  │
│  └──────────────┴────────────────┴──────────────────────┘  │
│  ┌──────────────┬────────────────┬──────────────────────┐  │
│  │  Terraform   │  Helm          │  Backup              │  │
│  │  Runner      │  Runner        │  Manager             │  │
│  └──────────────┴────────────────┴──────────────────────┘  │
└────────────────────┬───────────────────────┬────────────────┘
                     │                       │
                     │ Generates             │ Executes
                     ▼                       ▼
        ┌────────────────────┐   ┌──────────────────────┐
        │  terraform.tfvars  │   │   terraform apply    │
        │  custom-values.yaml│   │   helm install       │
        └────────────────────┘   └──────────┬───────────┘
                                            │
                                            │ Provisions
                                            ▼
                     ┌──────────────────────────────────────┐
                     │         AWS INFRASTRUCTURE            │
                     │                                       │
                     │  ┌──────────────┐  ┌──────────────┐ │
                     │  │  EC2 Mode    │  │  EKS Mode    │ │
                     │  │              │  │              │ │
                     │  │  - VPC       │  │  - VPC       │ │
                     │  │  - EC2       │  │  - EKS       │ │
                     │  │  - EIP       │  │  - Nodes     │ │
                     │  │  - SG        │  │  - Ingress   │ │
                     │  │  - IAM       │  │  - IAM       │ │
                     │  └──────────────┘  └──────────────┘ │
                     │                                       │
                     │  ┌──────────────────────────────────┐│
                     │  │  N8N Application                 ││
                     │  │  - Docker (EC2)                  ││
                     │  │  - Helm Chart (EKS)              ││
                     │  └──────────────────────────────────┘│
                     └───────────────────────────────────────┘
```

### 7.2 EKS Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        AWS Region                                │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  VPC (10.0.0.0/16)                                         │ │
│  │                                                             │ │
│  │  ┌──────────────────┐          ┌──────────────────────┐   │ │
│  │  │  Public Subnets  │          │  Private Subnets     │   │ │
│  │  │  (3 AZs)         │          │  (3 AZs)             │   │ │
│  │  │                  │          │                      │   │ │
│  │  │  ┌────────────┐  │          │  ┌────────────────┐ │   │ │
│  │  │  │ NLB        │  │          │  │ EKS Nodes      │ │   │ │
│  │  │  │ (Ingress)  │◄─┼──────────┼──│ (t3.medium x2) │ │   │ │
│  │  │  └────────────┘  │          │  │                │ │   │ │
│  │  │                  │          │  │  ┌──────────┐  │ │   │ │
│  │  │  ┌────────────┐  │          │  │  │ n8n Pod  │  │ │   │ │
│  │  │  │ NAT GW x3  │──┼─────────►│  │  └──────────┘  │ │   │ │
│  │  │  └────────────┘  │          │  │                │ │   │ │
│  │  │                  │          │  │  ┌──────────┐  │ │   │ │
│  │  │  ┌────────────┐  │          │  │  │ EBS PVC  │  │ │   │ │
│  │  │  │ IGW        │  │          │  │  │ (10Gi)   │  │ │   │ │
│  │  │  └────────────┘  │          │  │  └──────────┘  │ │   │ │
│  │  │                  │          │  └────────────────┘ │   │ │
│  │  └──────────────────┘          └──────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  EKS Control Plane (Managed)                               │ │
│  │  - Kubernetes 1.31                                         │ │
│  │  - Multi-AZ (AWS managed)                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  EKS Add-ons                                               │ │
│  │  - EBS CSI Driver (for persistent storage)                │ │
│  │  - NGINX Ingress Controller                               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  SSM Parameter Store                                       │ │
│  │  - /n8n/encryption_key (SecureString)                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  IAM Roles                                                 │ │
│  │  - EKS Cluster Role (eks.amazonaws.com)                    │ │
│  │  - Node Group Role (ec2.amazonaws.com)                     │ │
│  │  - EBS CSI Driver Role (IRSA)                              │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**Cost Breakdown:**
- EKS control plane: ~$73/month
- EC2 nodes (2x t3.medium): ~$60/month
- NAT Gateways (3x): ~$97/month
- NLB (for ingress): ~$16/month
- EBS volumes (10Gi): ~$1/month
- Data transfer: Variable (~$5-10/month)
- **Total: ~$252-262/month**

**Cost optimization options:**
- Use 1 NAT Gateway instead of 3 (saves ~$65/month, reduces HA)
- Use smaller nodes like t3.small (saves ~$30/month, reduces capacity)
- Reduce min/desired node count to 1 (saves ~$30/month, reduces HA)

---

### 7.3 Data Flow

#### 7.3.1 Setup Flow

```
┌─────────┐
│  START  │
└────┬────┘
     │
     ▼
┌──────────────────┐
│ Check Python     │
│ version >= 3.7   │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Check            │
│ dependencies     │
│ (terraform, aws, │
│  helm, kubectl)  │
└────┬────────────┘
     │
     │ Missing deps?
     ├──── YES ──────► Display install instructions ──► EXIT
     │
     │ NO
     ▼
┌──────────────────┐
│ Get AWS profiles │
│ from CLI config  │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Prompt user to   │
│ select profile   │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Validate AWS     │
│ credentials      │
│ (sts get-caller) │
└────┬────────────┘
     │
     │ Auth failed?
     ├──── YES ──────► Display error ──► EXIT
     │
     │ NO
     ▼
┌──────────────────┐
│ Prompt for AWS   │
│ region           │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Prompt for       │
│ EKS & n8n        │
│ configuration    │
│ (cluster name,   │
│  nodes, hostname,│
│  storage, etc.)  │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Prompt for n8n   │
│ encryption key   │
│ (generate or     │
│  provide)        │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Display config   │
│ summary and ask  │
│ for confirmation │
└────┬────────────┘
     │
     │ Confirmed?
     ├──── NO ───────► EXIT (no changes)
     │
     │ YES
     ▼
┌──────────────────┐
│ Create backups   │
│ of existing      │
│ config files     │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Write            │
│ terraform.tfvars │
│ with EKS config  │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ terraform init   │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ terraform plan   │
└────┬────────────┘
     │
     │ Plan failed?
     ├──── YES ──────► Restore backups ──► Display error ──► EXIT
     │
     │ NO
     ▼
┌──────────────────┐
│ terraform apply  │
└────┬────────────┘
     │
     │ Apply failed?
     ├──── YES ──────► Restore backups ──► Display error ──► EXIT
     │
     │ NO
     ▼
┌──────────────────┐
│ Get terraform    │
│ outputs          │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Configure kubectl│
│ for EKS cluster  │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Verify n8n pod   │
│ is running       │
│ (deployed by TF) │
└────┬────────────┘
     │
     ▼
┌──────────────────┐
│ Display success  │
│ message with     │
│ ingress URL and  │
│ next steps       │
└────┬────────────┘
     │
     ▼
┌─────────┐
│   END   │
└─────────┘
```

#### 7.3.2 Error Recovery Flow

```
┌──────────────┐
│ Error occurs │
│ during setup │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Catch exception  │
│ (signal handler  │
│  for Ctrl+C)     │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Check if backups │
│ exist            │
└──────┬───────────┘
       │
       │ Backups exist?
       ├──── YES ──────┐
       │                │
       │ NO             ▼
       │          ┌──────────────────┐
       │          │ Restore backups: │
       │          │ - variables.tf   │
       │          │ - values.yaml    │
       │          │ - terraform.tfvars│
       │          └────┬─────────────┘
       │               │
       │               ▼
       │          ┌──────────────────┐
       │          │ Delete backup    │
       │          │ files            │
       │          └────┬─────────────┘
       │               │
       │◄──────────────┘
       │
       ▼
┌──────────────────┐
│ Display error    │
│ message with     │
│ recovery steps   │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Exit with code 1 │
└──────────────────┘
```

---

## 8. Provisioning UX Design

### 8.1 CLI Interaction Flow

#### 8.1.1 Welcome

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│  🚀 N8N EKS Deployment Setup                              │
│  ══════════════════════════════════════════                │
│                                                            │
│  This tool will deploy n8n on AWS EKS.                    │
│                                                            │
│  What will be created:                                     │
│  • EKS cluster with managed node group                     │
│  • VPC with public/private subnets (3 AZs)                │
│  • NAT Gateways, Internet Gateway                         │
│  • EBS CSI driver for persistent storage                  │
│  • NGINX Ingress Controller                               │
│  • N8N deployed via Helm                                   │
│                                                            │
│  Estimated cost: ~$250-260/month                          │
│  Deployment time: ~25-30 minutes                          │
│                                                            │
└────────────────────────────────────────────────────────────┘

Press Enter to continue or Ctrl+C to exit: _
```

#### 8.1.2 Dependency Check Output

```
┌────────────────────────────────────────────────────────────┐
│  🔍 Checking dependencies...                              │
└────────────────────────────────────────────────────────────┘

✓ terraform - installed (v1.7.0)
✓ aws - installed (v2.15.0)
✓ helm - installed (v3.14.0)
✓ kubectl - installed (v1.29.0)

✓ All dependencies satisfied
```

#### 8.1.3 AWS Configuration

```
┌────────────────────────────────────────────────────────────┐
│  ☁️  AWS Configuration                                     │
└────────────────────────────────────────────────────────────┘

Available AWS profiles:
  1) default
  2) your-profile
  3) production

Select AWS profile [1-3] or enter profile name: 2

Validating credentials for profile 'your-profile'...
✓ Authenticated as: arn:aws:iam::123456789012:user/misael

Select AWS region:
  1) us-east-1 (N. Virginia)
  2) us-west-2 (Oregon)
  3) eu-west-1 (Ireland)
  4) ap-southeast-1 (Singapore)

Select region [1-4] (default: 1): 1

Using region: us-east-1
```

#### 8.1.4 EKS Configuration

```
┌────────────────────────────────────────────────────────────┐
│  ⚙️  EKS Deployment Configuration                          │
└────────────────────────────────────────────────────────────┘

EKS cluster name (default: n8n-eks-cluster): production-n8n

Node instance type:
  1) t3.small  (~$30/month for 2 nodes)
  2) t3.medium (~$60/month for 2 nodes) [Recommended]
  3) t3.large  (~$120/month for 2 nodes)

Select instance type [1-3] (default: 2): 2

Node group sizing:
  Minimum nodes (default: 1): 1
  Desired nodes (default: 2): 2
  Maximum nodes (default: 3): 3

N8N hostname (FQDN):
  This will be used for ingress and webhooks
  Example: n8n.yourdomain.com

Hostname: n8n.production.example.com

Kubernetes namespace (default: n8n): n8n

Persistent volume size (default: 10Gi): 10Gi

Timezone (default: America/Bahia): America/New_York
```

#### 8.1.5 Encryption Key Generation

```
┌────────────────────────────────────────────────────────────┐
│  🔐 N8N Encryption Key                                     │
└────────────────────────────────────────────────────────────┘

N8N requires an encryption key for sensitive data.

Generate a new encryption key? [Y/n] (default: Y): Y

✓ Generated encryption key:
  a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2

⚠️  IMPORTANT: Save this key securely!
   - You'll need it if migrating or restoring n8n
   - Loss of this key means loss of encrypted data
   - It will be stored in AWS SSM Parameter Store

Press Enter when you've saved the key: _
```

#### 8.1.6 TLS/Certificate Configuration

```
┌────────────────────────────────────────────────────────────┐
│  🔒 TLS/HTTPS Configuration                                │
└────────────────────────────────────────────────────────────┘

Configure TLS/HTTPS for your n8n instance?

  • Without TLS: Access via http://<load-balancer-dns>
  • With TLS: Access via https://<your-domain>

Configure TLS now? [y/N] (default: N): y

Domain name (FQDN):
  This will be used for ingress and HTTPS access
  Example: n8n.production.example.com

Domain: n8n.production.example.com

Certificate source:

  1) Bring your own certificate (BYO)
     - You provide certificate and private key files
     - Immediate setup, no waiting for validation

  2) Auto-generate via Let's Encrypt (Recommended)
     - Free SSL certificate
     - Automatic renewal
     - Requires DNS configuration first

  3) Configure later
     - Deploy without TLS now
     - Run 'python3 setup.py --update-tls' later

Select certificate source [1-3] (default: 2): 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Let's Encrypt Configuration:

Email address for certificate notifications:
  Required for Let's Encrypt certificate expiration warnings
  Example: admin@example.com

Email: admin@production.example.com

✓ Email validated

⚠️  IMPORTANT: Configure DNS before deployment!

Before Let's Encrypt can issue a certificate, you must:

1. Deploy the infrastructure (this will create a Network Load Balancer)
2. Get the NLB DNS name from the deployment output
3. Create a DNS record:
   Type: A or CNAME
   Name: n8n.production.example.com
   Value: <NLB-DNS-name> or <Elastic-IP>

Let's Encrypt will validate domain ownership via HTTP-01 challenge.
This requires your domain to resolve to the NLB.

Press Enter to continue: _
```

**Alternative: Bring Your Own Certificate**

```
┌────────────────────────────────────────────────────────────┐
│  🔒 TLS/HTTPS Configuration (BYO Certificate)              │
└────────────────────────────────────────────────────────────┘

Domain: n8n.production.example.com

Certificate file path (PEM format):
  Example: /path/to/certificate.crt or /path/to/fullchain.pem

Certificate file: /home/user/certs/n8n.crt

Private key file path (PEM format):
  Example: /path/to/private-key.key

Private key file: /home/user/certs/n8n.key

Validating certificate...
✓ Certificate file is valid PEM format
✓ Private key file is valid PEM format
✓ Certificate and private key match
✓ Certificate is valid for domain: n8n.production.example.com
✓ Certificate expires: 2026-10-05 (364 days remaining)

Certificate validated successfully!
```

**Alternative: Configure Later**

```
TLS configuration skipped.

You can configure TLS later by running:
  python3 setup.py --update-tls

Your n8n instance will be accessible via HTTP:
  http://<load-balancer-dns>
```

#### 8.1.7 Configuration Summary

```
┌────────────────────────────────────────────────────────────┐
│  📋 Configuration Summary                                  │
└────────────────────────────────────────────────────────────┘

AWS Profile:        your-profile
AWS Region:         us-east-1
Cluster Name:       production-n8n
Node Instance Type: t3.medium
Node Count:         Min: 1, Desired: 2, Max: 3
Namespace:          n8n
Storage Size:       10Gi
Timezone:           America/New_York
Encryption Key:     a1b2c3...e1f2 (64 chars)

TLS Configuration:
  Domain:           n8n.production.example.com
  Certificate:      Let's Encrypt (auto-generated)
  Email:            admin@production.example.com

Estimated Monthly Cost: $252-262

Resources to be created:
  ✓ VPC with public/private subnets (3 AZs)
  ✓ NAT Gateways (3x) and Internet Gateway
  ✓ EKS cluster (Kubernetes 1.31)
  ✓ Node group (2x t3.medium in private subnets)
  ✓ EBS CSI driver addon
  ✓ Default StorageClass (gp3, encrypted)
  ✓ NGINX Ingress Controller with NLB + Elastic IP
  ✓ IAM roles (cluster, nodes, IRSA for EBS)
  ✓ SSM parameter (encryption key, SecureString)
  ✓ cert-manager (for Let's Encrypt)
  ✓ ClusterIssuer (Let's Encrypt HTTP-01)
  ✓ N8N via Helm chart with TLS enabled

This configuration will be saved and applied using Terraform + Helm.

Proceed with deployment? [y/N]: y
```

#### 8.1.8 Deployment Progress

```
┌────────────────────────────────────────────────────────────┐
│  🚀 Starting Deployment                                    │
└────────────────────────────────────────────────────────────┘

Creating backups of existing configuration...
✓ Backup created: variables.tf.backup

Writing configuration files...
✓ Created: terraform/terraform.tfvars

Initializing Terraform...
✓ Terraform initialized

Planning infrastructure changes...
Plan: 12 to add, 0 to change, 0 to destroy

Applying Terraform configuration...
[This may take 5-10 minutes]

⏳ Creating VPC...                           ✓ Complete (15s)
⏳ Creating subnets...                        ✓ Complete (8s)
⏳ Creating internet gateway...               ✓ Complete (5s)
⏳ Creating security group...                 ✓ Complete (3s)
⏳ Creating IAM role...                       ✓ Complete (7s)
⏳ Storing encryption key in SSM...          ✓ Complete (2s)
⏳ Launching EC2 instance...                 ✓ Complete (45s)
⏳ Allocating Elastic IP...                  ✓ Complete (5s)
⏳ Installing Docker and n8n...              ✓ Complete (120s)

✓ Terraform apply completed successfully!
```

#### 8.1.9 Success & Next Steps

```
┌────────────────────────────────────────────────────────────┐
│  🎉 Deployment Complete!                                   │
└────────────────────────────────────────────────────────────┘

Your n8n instance is ready!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Access URL:      https://n8n.example.com
                 (DNS configuration required - see below)

Elastic IP:      54.123.45.67
Instance ID:     i-0abcdef1234567890

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 Next Steps:

1. Configure DNS:
   - Create an A record for 'n8n.example.com'
   - Point it to: 54.123.45.67
   - Wait for DNS propagation (5-30 minutes)

2. Access n8n:
   - Open: https://n8n.example.com
   - Create your admin account
   - Start building workflows!

3. View instance details:
   aws ec2 describe-instances --instance-ids i-0abcdef1234567890 \
     --profile <your-profile> --region us-east-1

aws ssm start-session --target i-0abcdef1234567890 \
     --profile <your-profile> --region us-east-1

5. View logs:
   aws ssm start-session --target i-0abcdef1234567890 \
     --profile <your-profile> --region us-east-1
   # Then in the session:
   cd /opt/n8n && docker-compose logs -f

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🗑️  To destroy this deployment:
   cd terraform && terraform destroy

📚 Documentation: https://docs.n8n.io/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 8.1.10 Error Display

```
┌────────────────────────────────────────────────────────────┐
│  ❌ Deployment Failed                                      │
└────────────────────────────────────────────────────────────┘

Error: AWS authentication failed

Details:
  Unable to locate credentials. You can configure credentials by
  running "aws configure" for profile '<your-profile>'.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 How to fix:

1. Configure AWS credentials:
   aws configure --profile <your-profile>

2. Verify credentials work:
   aws sts get-caller-identity --profile <your-profile>

3. Re-run setup:
   python3 setup.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Configuration files have been restored to their original state.
No changes were made to your infrastructure.

For more help, see: README.md
```

---

### 8.2 Color Coding Standards

| Message Type | Color | ANSI Code | Usage |
|--------------|-------|-----------|-------|
| Success | Green | `\033[92m` | ✓ Checkmarks, completion messages |
| Info | Cyan | `\033[96m` | URLs, commands, values |
| Warning | Yellow | `\033[93m` | Cost warnings, optional steps |
| Error | Red | `\033[91m` | Errors, failures, critical issues |
| Header | Magenta | `\033[95m` | Section headers, titles |
| Prompt | Blue | `\033[94m` | User input prompts |
| Bold | Bold | `\033[1m` | Important text, emphasis |

---

### 8.3 Input Validation Rules

| Field | Validation Rule | Error Message |
|-------|----------------|---------------|
| AWS Profile | Must exist in `~/.aws/config` | "Profile 'X' not found. Run: aws configure --profile X" |
| AWS Region | Must be valid AWS region code | "Invalid region. Choose from list or enter valid region code" |
| Encryption Key | Must be 64 hex characters (if provided) | "Encryption key must be 64 hexadecimal characters" |
| Domain Name | Must be valid FQDN format (if TLS enabled) | "Invalid domain format. Example: n8n.example.com" |
| Instance Type | Must match AWS instance type pattern | "Invalid instance type. Choose from list" |
| Timezone | Must be valid IANA timezone | "Invalid timezone. See: wikipedia.org/wiki/List_of_tz_database_time_zones" |
| Cluster Name | Alphanumeric + hyphens only, 1-100 chars | "Invalid cluster name. Use alphanumeric and hyphens only" |
| Namespace | Valid Kubernetes namespace (DNS label) | "Invalid namespace. Must be lowercase alphanumeric + hyphens" |
| Storage Size | Valid Kubernetes resource quantity | "Invalid size. Examples: 10Gi, 50Gi, 100Gi" |
| **TLS Certificate File** | Must be readable file path, valid PEM format | "Certificate file not found or invalid PEM format" |
| **TLS Private Key File** | Must be readable file path, valid PEM format | "Private key file not found or invalid PEM format" |
| **Certificate/Key Match** | Certificate must match private key | "Certificate and private key do not match" |
| **Certificate Expiration** | Certificate must not be expired | "Certificate has expired on <date>" |
| **Certificate Validity** | Certificate must be valid for provided domain | "Certificate is not valid for domain: <domain>" |
| **Email Address** | Valid email format (for Let's Encrypt) | "Invalid email format. Example: admin@example.com" |

---

### 8.4 Progress Indicators

For operations > 10 seconds, show progress:

```python
# Spinner for unknown duration
⏳ Initializing Terraform...

# Progress bar for known steps
Creating infrastructure: [████████████░░░░░░░░] 60% (6/10 resources)

# Step completion
✓ Creating VPC...                           ✓ Complete (15s)
```

---

## 9. Acceptance Criteria

### 9.1 Definition of Done

A feature is considered "done" when:
1. Code implemented and follows style guide
2. Unit tests written and passing (where applicable)
3. Manual testing completed successfully
4. Documentation updated
5. Error handling implemented
6. Backup/rollback tested
7. Reviewed by peer (if applicable)

### 9.2 Testing Checklist

**Pre-deployment:**
- [ ] Dependency check works with missing tools
- [ ] Dependency check works with all tools installed
- [ ] AWS profile detection works
- [ ] AWS authentication validation catches bad credentials
- [ ] Input validation rejects invalid values
- [ ] Ctrl+C during prompts restores backups
- [ ] Configuration summary displays all values correctly
- [ ] TLS configuration prompts work correctly
- [ ] Certificate file validation works (BYO option)
- [ ] Certificate/key mismatch detected
- [ ] Expired certificate detected
- [ ] Email validation works (Let's Encrypt option)

**EKS Deployment (No TLS):**
- [ ] Terraform creates VPC, subnets, NAT gateways
- [ ] EKS cluster created successfully
- [ ] Node group created with correct instance types
- [ ] EBS CSI driver addon installed
- [ ] NLB created with static Elastic IP
- [ ] kubectl configured automatically
- [ ] Helm chart installs successfully
- [ ] n8n pod reaches Running state
- [ ] PVC binds to EBS volume
- [ ] Ingress created (HTTP only, no TLS)
- [ ] n8n accessible via http://<nlb-dns>
- [ ] Can create n8n admin account
- [ ] Workflows can be created and executed
- [ ] Persistent data survives pod restart
- [ ] Encryption key stored in SSM

**EKS Deployment (with Let's Encrypt TLS):**
- [ ] cert-manager deployed successfully
- [ ] ClusterIssuer created for Let's Encrypt
- [ ] Ingress configured with TLS annotations
- [ ] Certificate request created
- [ ] HTTP-01 challenge completes (after DNS configured)
- [ ] Certificate issued by Let's Encrypt
- [ ] TLS Secret created in correct namespace
- [ ] n8n accessible via https://<domain>
- [ ] HTTP redirects to HTTPS
- [ ] Certificate is valid and trusted
- [ ] Certificate auto-renewal configured (30 days before expiry)

**EKS Deployment (with BYO Certificate):**
- [ ] Certificate file read successfully
- [ ] Private key file read successfully
- [ ] TLS Secret created with provided certificate
- [ ] Ingress configured with TLS enabled
- [ ] n8n accessible via https://<domain>
- [ ] Certificate serves correctly
- [ ] Certificate matches provided domain

**TLS Updates (Post-Deployment):**
- [ ] `setup.py --update-tls` command works
- [ ] Can add TLS to existing non-TLS deployment
- [ ] Can update BYO certificate without downtime
- [ ] New certificate serves immediately
- [ ] Old certificate backed up before replacement
- [ ] Can switch from BYO to Let's Encrypt
- [ ] Can switch from Let's Encrypt to BYO
- [ ] Ingress configuration updates correctly
- [ ] No pod restarts required for certificate updates
- [ ] TLS update doesn't affect application data

**Error Handling:**
- [ ] Terraform errors displayed clearly
- [ ] Backups restored on Ctrl+C
- [ ] Backups restored on Terraform failure
- [ ] AWS auth errors show helpful message
- [ ] Missing dependency errors show install instructions
- [ ] Invalid input rejected with clear error

**Cleanup:**
- [ ] `terraform destroy` removes all EKS resources
- [ ] `terraform destroy` removes cert-manager (if deployed)
- [ ] `terraform destroy` removes NLB and Elastic IP
- [ ] No orphaned resources left in AWS (check TLS secrets, certificates)
- [ ] Local backup files cleaned up

---

## 10. Success Criteria

### 10.1 User Success Metrics

The deployment is considered successful when:

1. **Time to Deploy**
   - EKS deployment: Complete in < 30 minutes
   - With Let's Encrypt: Add 2-5 minutes for certificate issuance (after DNS configured)

2. **User Experience**
   - User completes deployment without consulting documentation
   - No Python errors shown to user
   - Clear feedback at every step

3. **Infrastructure Quality**
   - All AWS resources follow best practices
   - Security groups properly configured
   - Encryption enabled for data at rest
   - Private subnets used for compute

4. **Application Health**
   - n8n accessible via provided URL
   - Can create admin account
   - Can create and execute workflow
   - Data persists across restarts

5. **Cost Accuracy**
   - Actual AWS costs within 10% of estimates
   - No unexpected charges

### 10.2 Project Success Criteria

The project is considered successful when:

1. **Adoption**: 10+ successful deployments by users outside development team
2. **Satisfaction**: 80%+ user satisfaction rating
3. **Support Load**: < 5% of deployments require manual support intervention
4. **Documentation**: 90%+ of questions answerable from README/docs
5. **Reliability**: 95%+ success rate for deployments (first attempt)

---

## 11. Future Enhancements (Out of Scope for v1.0)

These features are acknowledged but not included in initial release:

1. **Multi-region deployments**
2. **RDS PostgreSQL integration** (currently uses SQLite)
3. **Redis integration** for queue mode
4. **Backup/restore automation**
5. **Monitoring stack** (Prometheus, Grafana)
6. **GitOps integration** (ArgoCD, Flux)
7. **Cost optimization recommendations**
8. **Automatic scaling policies**
9. **Disaster recovery planning**
10. **Blue/green deployments**
11. **Spot instance support**
12. **Private VPC endpoints** (no internet access)

---

## 12. Appendices

### Appendix A: Glossary

| Term | Definition |
|------|------------|
| n8n | Workflow automation platform (similar to Zapier, but self-hosted) |
| EKS | Amazon Elastic Kubernetes Service |
| EC2 | Amazon Elastic Compute Cloud (virtual servers) |
| VPC | Virtual Private Cloud (isolated network in AWS) |
| NAT Gateway | Network Address Translation gateway (allows private instances to access internet) |
| NLB | Network Load Balancer |
| EBS | Elastic Block Store (persistent disk storage) |
| IRSA | IAM Roles for Service Accounts (Kubernetes to AWS auth) |
| SSM | AWS Systems Manager (includes Parameter Store for secrets) |
| PVC | PersistentVolumeClaim (Kubernetes storage request) |
| FQDN | Fully Qualified Domain Name (e.g., n8n.example.com) |
| IANA | Internet Assigned Numbers Authority (maintains timezone database) |

### Appendix B: AWS Permissions Required

The AWS credentials used must have permissions to create:

**IAM:**
- Roles, policies, instance profiles

**EC2:**
- VPCs, subnets, route tables, internet gateways, NAT gateways
- Security groups
- EC2 instances
- Elastic IPs
- Key pairs (optional)

**EKS:**
- EKS clusters
- Node groups
- EKS addons

**SSM:**
- Parameters (SecureString)

**ELB:**
- Load balancers (for EKS ingress)

Example IAM policy: (for production, tighten further)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "eks:*",
        "iam:*",
        "ssm:*",
        "elasticloadbalancing:*"
      ],
      "Resource": "*"
    }
  ]
}
```

---

**Document Version History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-05 | System | Initial requirements document |

---

**Document Status**: Draft - Awaiting Review
