# N8N AWS Deployment Automation - Requirements Document

**Version**: 1.3
**Date**: 2025-10-15
**Status**: Updated

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
**User Story**: As a user, I want flexible TLS configuration options as a post-deployment step to avoid race conditions with certificate validation.

**Requirements**:

**4-Phase Deployment Workflow:**

TLS configuration is handled in **Phase 4** (post-deployment) to prevent race conditions with Let's Encrypt validation:

1. **Phase 1**: Terraform deploys infrastructure (VPC, EKS, NGINX ingress)
2. **Phase 2**: Helm deploys n8n application with HTTP only
3. **Phase 3**: LoadBalancer URL is retrieved and displayed
4. **Phase 4**: Optional interactive TLS configuration

**Initial Deployment (Phases 1-3):**
- n8n is **always deployed with HTTP initially** (no TLS)
- Access n8n via LoadBalancer DNS: `http://<load-balancer-dns>`
- No TLS configuration during infrastructure deployment
- Prevents cert-manager from requesting certificates before LoadBalancer exists

**Phase 4: Post-Deployment Configuration (TLS & Basic Auth)**

After the LoadBalancer is ready, users are prompted for post-deployment configuration:

**Step 1: TLS Configuration**

Users are prompted: **"Would you like to configure TLS/HTTPS now?"**

If **Yes**, two options are available:

1. **Option 1: Bring Your Own Certificate**
   - User provides TLS certificate and private key (PEM format)
   - Setup validates certificate format
   - Certificate stored as Kubernetes Secret (`n8n-tls`)
   - n8n Helm release upgraded with `tls.enabled=true`
   - Access n8n via `https://<your-domain>`

2. **Option 2: Let's Encrypt (Auto-generated)**
   - **Critical**: LoadBalancer DNS is displayed to user
   - Setup instructs: "Configure DNS to point `<your-domain>` to `<load-balancer-dns>`"
   - User **must confirm DNS is configured** before proceeding
   - Setup deploys cert-manager via Helm
   - Setup creates ClusterIssuer for Let's Encrypt (HTTP-01 validation)
   - n8n Helm release upgraded with TLS and cert-manager annotations
   - Let's Encrypt validates domain ownership via HTTP-01
   - Certificate issued (~2-5 minutes)
   - Certificate auto-renewed before expiration
   - Access n8n via `https://<your-domain>`

If **No** (skip TLS):
- User can configure TLS later using `python3 setup.py --configure-tls` (feature planned)
- User can manually configure TLS using Helm upgrade commands

**Step 2: Basic Authentication Configuration**

After TLS configuration (or if TLS is skipped), users are prompted: **"Would you like to enable basic authentication for the application?"**

If **Yes**:
- Setup auto-generates basic auth credentials:
  - Username: `admin`
  - Password: 12 random alphanumeric characters
- Credentials are stored in AWS Secrets Manager (`/n8n/basic-auth`)
- Credentials are displayed to user (must save them)
- Ingress is updated with basic auth configuration (nginx auth annotations)
- Basic auth protects both HTTP and HTTPS access to n8n
- User must authenticate before accessing n8n web interface

If **No** (skip basic auth):
- n8n is publicly accessible via LoadBalancer URL
- User can enable basic auth later (feature planned)

**Post-Deployment Certificate Updates:**

The tool must support updating TLS configuration after deployment:

1. **Add TLS to existing HTTP-only deployment**
   - Re-run setup.py with `--configure-tls` flag (planned)
   - Prompt for domain and certificate option
   - Update n8n Helm release with TLS enabled
   - No downtime required (rolling update)

2. **Update existing certificates (BYO)**
   - Update Kubernetes Secret with new certificate
   - Ingress automatically picks up new certificate
   - No pod restart required

3. **Switch from BYO to Let's Encrypt (or vice versa)**
   - Remove old certificate resources
   - Configure new certificate option
   - Update n8n Helm release
   - Minimal downtime during certificate switch

**Technical Implementation:**

- **LoadBalancer**: NGINX ingress creates Network Load Balancer (NLB) with static Elastic IPs automatically
- **Static Elastic IPs**: Three EIPs allocated (one per AZ) and attached to NLB for consistent DNS A-record mapping
- **Namespace Configuration**: All kubectl/helm operations honor the user-configured namespace (default: n8n)
- **DNS Confirmation**: Required before Let's Encrypt proceeds (prevents HTTP-01 validation failures)
- **Cert-Manager Integration**: Deployed via Helm in Phase 4 (version 1.13.3)
- **ClusterIssuer Configuration**: HTTP-01 challenge via ingress class nginx
- **Certificate Storage**: Kubernetes TLS secrets in configured namespace
- **Helm Upgrade Strategy**:
  - Initial deploy: `helm install n8n ./helm --set ingress.tls.enabled=false --set persistence.size=<configured>`
  - Deployment readiness: `kubectl wait --for=condition=available deployment/n8n` (5-minute timeout)
  - TLS upgrade: `helm upgrade n8n ./helm --reuse-values --set ingress.tls.enabled=true`
  - Basic Auth upgrade: `helm upgrade n8n ./helm --reuse-values --set ingress.basicAuth.enabled=true`
- **Certificate Monitoring**: cert-manager auto-renewal (30 days before expiration)
- **Race Condition Prevention**: LoadBalancer must exist and DNS must resolve before certificate request
- **Database Credentials**: Stored in AWS Secrets Manager and Kubernetes Secrets (never in Helm values)
- **Basic Auth Security**: Bcrypt password hashing (no SHA-1 fallback), credentials in Secrets Manager

**Acceptance Criteria**:

**Initial Deployment (HTTP only):**
- [x] Phase 1 completes: Infrastructure deployed via Terraform
- [x] Phase 2 completes: n8n deployed via Helm with HTTP only
- [x] Phase 3 completes: LoadBalancer URL retrieved and displayed
- [x] No TLS configuration during Phases 1-3
- [x] User can access n8n via HTTP at LoadBalancer URL

**Phase 4: TLS Configuration:**
- [ ] User prompted for TLS configuration after LoadBalancer is ready
- [ ] User can skip TLS configuration
- [ ] BYO certificate option validates PEM format
- [ ] Let's Encrypt option displays LoadBalancer URL for DNS configuration
- [ ] Let's Encrypt option requires DNS confirmation before proceeding
- [ ] cert-manager installed only if Let's Encrypt selected
- [ ] n8n Helm release upgraded with TLS enabled
- [ ] HTTP-01 validation completes successfully
- [ ] Certificate issued and ingress serves HTTPS traffic
- [ ] Access via HTTPS works with valid certificate

**Certificate Updates:**
- [ ] User can configure TLS using `--configure-tls` flag (planned)
- [ ] User can update BYO certificates without downtime
- [ ] User can manually switch between BYO and Let's Encrypt
- [ ] Certificate updates don't require pod restarts

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

#### FR-8: Basic Authentication

**Priority**: SHOULD HAVE
**User Story**: As a user, I want to protect my n8n instance with basic authentication to prevent unauthorized access while the application is exposed via public LoadBalancer.

**Requirements**:

**Basic Auth Configuration (Phase 4):**
- After TLS configuration, prompt user for basic authentication
- Auto-generate credentials:
  - Username: `admin` (fixed)
  - Password: 12 random alphanumeric characters (auto-generated)
- Store credentials in AWS Secrets Manager (`/n8n/basic-auth`)
- Display credentials to user once (user must save them)
- Configure NGINX ingress with basic auth annotations
- Create Kubernetes Secret for auth file (htpasswd format)
- Apply basic auth to all ingress paths

**Technical Implementation:**
- Use `htpasswd` utility to generate bcrypt password hash
- Create Kubernetes Secret: `n8n-basic-auth` with auth file
- Update ingress annotations:
  - `nginx.ingress.kubernetes.io/auth-type: basic`
  - `nginx.ingress.kubernetes.io/auth-secret: n8n-basic-auth`
  - `nginx.ingress.kubernetes.io/auth-realm: "Authentication Required - N8N"`
- Helm upgrade to apply basic auth configuration
- Store credentials in AWS Secrets Manager for backup/recovery

**Acceptance Criteria**:
- [ ] User prompted for basic auth after TLS configuration
- [ ] Credentials auto-generated securely
- [ ] Username is always `admin`
- [ ] Password is 12 random alphanumeric characters
- [ ] Credentials stored in AWS Secrets Manager
- [ ] Credentials displayed to user with warning to save
- [ ] NGINX ingress configured with basic auth
- [ ] Basic auth applies to HTTP and HTTPS access
- [ ] Authentication required before accessing n8n web interface
- [ ] Invalid credentials rejected by ingress
- [ ] Valid credentials grant access to n8n

**Security Considerations**:
- Password generated using cryptographically secure random
- Password hashed with bcrypt before storing in Kubernetes Secret
- Credentials never logged in plaintext
- AWS Secrets Manager provides backup of credentials
- User warned to save credentials securely

---

#### FR-9: Database Selection (SQLite vs PostgreSQL)

**Priority**: SHOULD HAVE
**User Story**: As a user, I want to choose between SQLite and PostgreSQL as my n8n database backend based on my scalability and reliability needs.

**Requirements**:

**Database Selection Prompt (Phase 1 - Terraform Configuration):**
- During initial configuration, prompt user for database choice:
  - Option 1: SQLite (default, simpler, file-based)
  - Option 2: PostgreSQL (RDS, production-grade, scalable)
- If SQLite selected:
  - Use local file storage on EBS volume
  - No additional infrastructure required
  - Lower cost (~$1/month for EBS storage)
- If PostgreSQL selected:
  - Provision RDS PostgreSQL instance
  - Prompt for RDS configuration:
    - Instance class (db.t3.micro, db.t3.small, db.t3.medium) [default: db.t3.micro]
    - Storage size (default: 20GB)
    - Multi-AZ deployment (yes/no) [default: no]
  - Configure n8n with PostgreSQL connection
  - Store DB credentials in AWS Secrets Manager

**RDS Provisioning (when PostgreSQL selected):**
- Create RDS subnet group in private subnets
- Create RDS security group (allow access from EKS nodes only)
- Provision RDS PostgreSQL instance (version 15.14+)
- Generate random database password
- Store credentials in AWS Secrets Manager (`/n8n/db-credentials`)
- Configure n8n Helm chart with PostgreSQL environment variables:
  - `DB_TYPE=postgresdb`
  - `DB_POSTGRESDB_HOST=<rds-endpoint>`
  - `DB_POSTGRESDB_PORT=5432`
  - `DB_POSTGRESDB_DATABASE=n8n`
  - `DB_POSTGRESDB_USER=n8n_user`
  - `DB_POSTGRESDB_PASSWORD=<from-secrets-manager>`

**Acceptance Criteria**:
- [ ] User prompted for database choice during configuration
- [ ] SQLite selected by default
- [ ] PostgreSQL option triggers RDS provisioning
- [ ] RDS instance created in private subnets
- [ ] RDS security group restricts access to EKS nodes only
- [ ] Database credentials auto-generated and stored in Secrets Manager
- [ ] n8n configured correctly for selected database type
- [ ] SQLite uses persistent EBS volume
- [ ] PostgreSQL uses RDS endpoint
- [ ] Database connection tested before deployment completes
- [ ] Data persists across n8n pod restarts (both SQLite and PostgreSQL)

**Cost Considerations**:
- SQLite: ~$1/month (EBS storage only)
- PostgreSQL (RDS db.t3.micro): ~$15/month (single-AZ) or ~$30/month (multi-AZ)
- PostgreSQL (RDS db.t3.small): ~$30/month (single-AZ) or ~$60/month (multi-AZ)
- PostgreSQL storage: ~$0.115/GB-month (20GB = ~$2.30/month)
- Display cost estimate to user based on selection

---

#### FR-10: Infrastructure Provisioning

**Priority**: MUST HAVE
**User Story**: As a user, I want the tool to automatically provision all required AWS EKS infrastructure.

**Requirements**:

**Must Create:**
- VPC with public/private subnets across 3 AZs
- NAT Gateway (1 shared across all AZs) for private subnet internet access
- Internet Gateway for public subnet access
- Route tables for public and private subnets
- EKS cluster (version 1.31)
- Node group in private subnets
- EBS CSI driver addon
- Default StorageClass for EBS volumes (gp3)
- IAM roles for cluster and nodes (IRSA for EBS CSI)
- SSM Parameter for encryption key (SecureString)
- n8n Helm release with proper configuration

**Conditionally Create (based on configuration):**
- NGINX Ingress Controller with Network Load Balancer - if `enable_nginx_ingress` is true
- Static Elastic IPs for NLB (one per AZ) - if NGINX ingress enabled

**Conditionally Create (based on user configuration):**

*TLS Configuration:*
- cert-manager (v1.13+) via Helm - if user selects Let's Encrypt option
- ClusterIssuer for Let's Encrypt (HTTP-01 challenge) - if using Let's Encrypt
- Kubernetes TLS Secret - if user provides BYO certificates
- Ingress TLS configuration - if TLS enabled

*Basic Authentication:*
- Kubernetes Secret for basic auth (htpasswd format) - if basic auth enabled
- Ingress basic auth annotations - if basic auth enabled
- AWS Secrets Manager secret for credentials backup - if basic auth enabled

*Database Configuration:*
- RDS PostgreSQL instance (version 15.14+) - if PostgreSQL selected (instead of SQLite)
- RDS subnet group in private subnets - if PostgreSQL selected
- RDS security group - if PostgreSQL selected
- AWS Secrets Manager secret for DB credentials - if PostgreSQL selected

**Acceptance Criteria**:
- All resources tagged appropriately with Name and Project tags
- EC2 instances (EKS nodes) have descriptive tags (Name, Description, NodeGroup, ManagedBy)
- IAM roles have Name tags for easy identification
- SSM parameters include descriptions and Name tags
- Secrets Manager secrets include Name tags
- EKS addons include Name tags
- All resources easily identifiable in AWS console
- Infrastructure follows AWS best practices
- Private subnets used for compute workloads (nodes)
- Encryption enabled where applicable (EBS, SSM, RDS)
- Least privilege IAM policies
- Multi-AZ deployment for high availability
- NLB has static Elastic IP allocated
- cert-manager only deployed if Let's Encrypt selected
- TLS configuration applied correctly based on user choice
- Basic auth configured correctly if user enables it
- RDS provisioned only if PostgreSQL selected
- Database credentials stored securely in Secrets Manager
- n8n configured with correct database backend

---

#### FR-11: Terraform Execution

**Priority**: MUST HAVE
**User Story**: As a user, I want the tool to run Terraform commands automatically and show me the results.

**Requirements**:
- Run `terraform init` in terraform directory
- Generate `terraform.tfvars` with user configuration
- Run `terraform plan` and show summary
- Prompt user to confirm plan
- Run `terraform apply` and rely on its interactive confirmation prompt
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

#### FR-12: Helm Deployment

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

#### FR-13: Post-Deployment Information

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

#### FR-14: Error Handling & Recovery

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

#### FR-15: File Modification Strategy

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

#### FR-16: Resource Naming and Tagging

**Priority**: MUST HAVE
**User Story**: As a user, I want all AWS resources properly named and tagged so I can easily identify and manage them in the AWS console.

**Requirements**:
- All resources must have a `Name` tag with descriptive identifier
- All resources must have a `Project` tag for resource grouping
- EC2 instances (EKS nodes) must have additional metadata tags:
  - `Description`: Brief description of resource purpose
  - `NodeGroup`: Reference to EKS node group
  - `ManagedBy`: "EKS" to indicate managed resource
- IAM roles must have `Name` tags matching their resource names
- SSM parameters must include:
  - `description` field explaining parameter purpose
  - `Name` tag for console visibility
- Secrets Manager secrets must have descriptive `Name` tags
- EKS addons must have `Name` tags
- Security groups must have both `name` and `description` fields
- All tags follow consistent naming convention: `{project_tag}-{resource-type}-{identifier}`

**Acceptance Criteria**:
- All AWS resources have `Name` and `Project` tags
- EC2 instances easily identifiable in EC2 console
- IAM roles easily identifiable in IAM console
- SSM parameters include descriptions and are easily searchable
- Secrets Manager secrets easily identifiable
- No resources appear as "unnamed" or with generic IDs only
- Tag values use project-specific prefix for filtering
- Resources can be filtered by project tag for cost tracking
- All resource names are human-readable and descriptive

---

#### FR-17: Security Best Practices

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
- EKS deployment (SQLite): $150-260/month (control plane ~$73 + nodes ~$60 + NAT gateways ~$97 + NLB ~$16 + EBS ~$1)
- EKS deployment (PostgreSQL): $165-290/month (add ~$15-30/month for RDS db.t3.micro, or ~$30-60/month for db.t3.small)

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
│  │  │  │ NAT GW     │──┼─────────►│  │  └──────────┘  │ │   │ │
│  │  │  │ (1 shared) │  │          │  │                │ │   │ │
│  │  │  └────────────┘  │          │  │  ┌──────────┐  │ │   │ │
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
│  │  - NGINX Ingress Controller (optional, configurable)      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  AWS Secrets Manager                                       │ │
│  │  - /n8n/encryption_key (n8n encryption key)                │ │
│  │  - /n8n/basic-auth (admin credentials - if enabled)        │ │
│  │  - /n8n/db-credentials (RDS credentials - if PostgreSQL)   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  RDS PostgreSQL (Optional - if selected instead of SQLite)│ │
│  │  - PostgreSQL 15.14+ in private subnets                    │ │
│  │  - Single-AZ by default (Multi-AZ option available)        │ │
│  │  - db.t3.micro (default), db.t3.small, or db.t3.medium    │ │
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

**Cost Breakdown (SQLite):**
- EKS control plane: ~$73/month
- EC2 nodes (2x t3.medium): ~$60/month
- NAT Gateway (1 shared): ~$32/month
- NLB (optional, for ingress): ~$16/month (if NGINX ingress enabled)
- EBS volumes (10Gi): ~$1/month
- Data transfer: Variable (~$5-10/month)
- **Total: ~$171-181/month (without NLB) or ~$187-197/month (with NLB)**

**Cost Breakdown (PostgreSQL/RDS):**
- Base EKS costs: ~$171-197/month (same as above, depending on NLB)
- RDS db.t3.micro (single-AZ): ~$15/month [default]
- RDS db.t3.micro (multi-AZ): ~$30/month
- RDS db.t3.small (single-AZ): ~$30/month
- RDS db.t3.small (multi-AZ): ~$60/month
- RDS storage (20GB): ~$2.30/month
- **Total: ~$188-259/month (depending on RDS and NLB configuration)**

**Cost optimization options (already applied by default):**
- ✓ Use 1 NAT Gateway shared across AZs (saves ~$65/month vs 3 NAT gateways)
- ✓ Disable NGINX ingress by default (saves ~$16/month, use LoadBalancer or NodePort instead)
- ✓ Use single-AZ RDS by default (saves ~$15/month vs multi-AZ for db.t3.micro)
- Use smaller nodes like t3.small (saves ~$30/month, reduces capacity)
- Reduce min/desired node count to 1 (saves ~$30/month, reduces HA)
- Use SQLite instead of PostgreSQL (saves ~$15-60/month, reduces scalability)

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
│  Estimated cost: ~$170-200/month (optimized for cost)                          │
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

Estimated Monthly Cost: $170-200 (optimized)

Resources to be created:
  ✓ VPC with public/private subnets (3 AZs)
  ✓ NAT Gateway (1 shared) and Internet Gateway
  ✓ EKS cluster (Kubernetes 1.31)
  ✓ Node group (2x t3.medium in private subnets)
  ✓ EBS CSI driver addon
  ✓ Default StorageClass (gp3, encrypted)
  ✓ NGINX Ingress Controller with NLB + Elastic IPs (optional, configurable)
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

**Resource Naming & Tagging:**
- [ ] All EC2 instances have Name tags
- [ ] EC2 instances have Description, NodeGroup, ManagedBy tags
- [ ] All IAM roles have Name tags
- [ ] SSM parameters have descriptions and Name tags
- [ ] Secrets Manager secrets have Name tags
- [ ] EKS addons have Name tags
- [ ] All resources have Project tags
- [ ] Resources easily identifiable in AWS console (EC2, IAM, Systems Manager, Secrets Manager)
- [ ] Resources can be filtered by project tag
- [ ] No resources appear with generic IDs only

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

**Basic Authentication:**
- [ ] User prompted for basic auth in Phase 4
- [ ] Credentials auto-generated (username: admin, password: 12 chars)
- [ ] Credentials displayed to user once
- [ ] Credentials stored in AWS Secrets Manager
- [ ] Kubernetes Secret created with htpasswd format
- [ ] Ingress configured with basic auth annotations
- [ ] Basic auth required for HTTP access
- [ ] Basic auth required for HTTPS access
- [ ] Invalid credentials rejected at ingress level
- [ ] Valid credentials grant access to n8n
- [ ] Can skip basic auth configuration
- [ ] n8n publicly accessible if basic auth skipped

**Database Selection (SQLite vs PostgreSQL):**
- [ ] User prompted for database choice during configuration
- [ ] SQLite selected by default
- [ ] PostgreSQL option triggers RDS configuration prompts
- [ ] RDS instance class selectable (db.t3.micro, db.t3.small, db.t3.medium)
- [ ] RDS storage size configurable (default 20GB)
- [ ] Multi-AZ option available for RDS
- [ ] RDS provisioned in private subnets
- [ ] RDS security group created and configured
- [ ] RDS security group allows access from EKS nodes only
- [ ] Database credentials auto-generated for PostgreSQL
- [ ] DB credentials stored in AWS Secrets Manager
- [ ] n8n configured with SQLite (file-based) when SQLite selected
- [ ] n8n configured with PostgreSQL connection when PostgreSQL selected
- [ ] Database connection tested before deployment completes
- [ ] Data persists in SQLite (EBS volume)
- [ ] Data persists in PostgreSQL (RDS)
- [ ] Cost estimate displayed based on database selection

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
- [ ] `terraform destroy` removes RDS instance (if PostgreSQL was selected)
- [ ] `terraform destroy` removes AWS Secrets Manager secrets
- [ ] No orphaned resources left in AWS (check TLS secrets, certificates, RDS snapshots)
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
   - All resources properly named and tagged (Name, Project tags)
   - Resources easily identifiable in AWS console
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
2. **Redis integration** for queue mode
3. **Backup/restore automation**
4. **Monitoring stack** (Prometheus, Grafana)
5. **GitOps integration** (ArgoCD, Flux)
6. **Cost optimization recommendations**
7. **Automatic scaling policies**
8. **Disaster recovery planning**
9. **Blue/green deployments**
10. **Spot instance support**
11. **Private VPC endpoints** (no internet access)

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

**Secrets Manager:**
- Secrets (for encryption key, basic auth, database credentials)

**RDS (if PostgreSQL selected):**
- DB instances
- DB subnet groups
- DB parameter groups
- DB security groups

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
        "secretsmanager:*",
        "rds:*",
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
| 1.1 | 2025-10-05 | System | Added FR-8 (Basic Authentication), FR-9 (Database Selection - SQLite vs PostgreSQL), updated Phase 4 to include basic auth configuration, added RDS provisioning requirements, updated cost estimates, updated acceptance criteria |
| 1.2 | 2025-10-09 | System | **Cost Optimizations Applied**: Reduced NAT Gateways from 3 to 1 shared (saves ~$65/month), disabled NGINX ingress by default (saves ~$16/month), changed RDS to single-AZ by default (saves ~$15/month), updated PostgreSQL version to 15.14, updated all cost estimates to reflect optimizations (~$170-200/month vs ~$250-260/month) |
| 1.3 | 2025-10-15 | System | **Resource Naming & Tagging Improvements**: Added FR-16 (Resource Naming and Tagging) as new requirement, enhanced tagging for EC2 instances (EKS nodes) with Name, Description, NodeGroup, and ManagedBy tags, added Name tags to all IAM roles, added descriptions and Name tags to SSM parameters, added Name tags to Secrets Manager secrets and EKS addons, improved acceptance criteria to include resource naming standards, all AWS resources now easily identifiable in console |

---

**Document Status**: Updated - Reflects deployed architecture
