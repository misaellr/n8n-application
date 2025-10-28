# GCP GKE Requirements Guide

Validated requirements for deploying n8n on Google Kubernetes Engine (GKE), based on successful AWS EKS and Azure AKS implementations.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Required Tools](#required-tools)
- [GCP Account Setup](#gcp-account-setup)
- [IAM Permissions](#iam-permissions)
- [Service Account Roles](#service-account-roles)
- [Required APIs](#required-apis)
- [Workload Identity Configuration](#workload-identity-configuration)
- [Cost Estimates](#cost-estimates)
- [Architecture Overview](#architecture-overview)
- [Common Pitfalls](#common-pitfalls)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### GCP Account Requirements

- **Active GCP Project**: A Google Cloud project with billing enabled
- **Project-level Access**: Sufficient permissions to create resources (see [IAM Permissions](#iam-permissions))
- **Billing Account**: Linked billing account with valid payment method
- **API Quota**: Default quotas are usually sufficient; increase if needed

### Local Development Environment

- **Operating System**: Linux, macOS, or WSL2 on Windows
- **Internet Access**: Required for downloading tools and accessing GCP APIs
- **Terminal/Shell**: Bash or compatible shell

## Required Tools

### Core Tools Installation

#### macOS (using Homebrew)

```bash
# Google Cloud SDK
brew install --cask google-cloud-sdk

# GKE gcloud auth plugin (REQUIRED for kubectl authentication)
gcloud components install gke-gcloud-auth-plugin

# Terraform
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

# kubectl
brew install kubectl

# Helm
brew install helm

# Python (if not already installed)
brew install python@3.11
```

#### Linux (Ubuntu/Debian)

```bash
# Google Cloud SDK
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
sudo apt-get update && sudo apt-get install google-cloud-sdk

# GKE gcloud auth plugin (REQUIRED for kubectl authentication)
# CRITICAL: This plugin is MANDATORY for Kubernetes 1.25+ clusters
sudo apt-get install -y google-cloud-cli-gke-gcloud-auth-plugin

# Terraform
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Python
sudo apt-get update
sudo apt-get install python3 python3-pip
```

### Verify Installation

```bash
# Check versions
gcloud --version                    # Should be latest (e.g., 400.0.0+)
gke-gcloud-auth-plugin --version    # REQUIRED - verify plugin is installed
terraform --version                 # >= 1.6.0
kubectl version --client            # >= 1.28.0
helm version                        # >= 3.12.0
python3 --version                   # >= 3.8
```

### ⚠️ CRITICAL: gke-gcloud-auth-plugin Requirement

**Starting with Kubernetes 1.25, the `gke-gcloud-auth-plugin` is MANDATORY for kubectl authentication to GKE clusters.**

**Why it's required:**
- Replaces the deprecated built-in kubectl auth provider
- Provides secure authentication using GCP IAM
- Acts as a bridge between gcloud credentials and kubectl
- Required by GCP for all GKE clusters running Kubernetes 1.25+

**Without this plugin:**
- `gcloud container clusters get-credentials` will fail
- kubectl commands will fail with authentication errors
- You cannot access your GKE cluster

**Installation verification:**
```bash
# Verify the plugin is installed and accessible
gke-gcloud-auth-plugin --version

# Expected output:
# Kubernetes v1.28.0 or similar
```

**If you see this error:**
```
CRITICAL: ACTION REQUIRED: gke-gcloud-auth-plugin, which is needed for
continued use of kubectl, was not found or is not executable
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install -y google-cloud-cli-gke-gcloud-auth-plugin

# macOS
gcloud components install gke-gcloud-auth-plugin

# Then verify
gke-gcloud-auth-plugin --version
```

## GCP Account Setup

### 1. Authenticate with Google Cloud

#### Option A: User Account (Recommended for Development)

```bash
# Initialize gcloud and authenticate
gcloud init

# Login to your Google account
gcloud auth login

# Set your project
gcloud config set project PROJECT_ID

# Verify authentication
gcloud auth list
gcloud config list
```

#### Option B: Service Account (Recommended for CI/CD)

```bash
# Create a service account
gcloud iam service-accounts create n8n-deployer \
  --display-name="N8N Deployment Service Account" \
  --project=PROJECT_ID

# Generate service account key
gcloud iam service-accounts keys create ~/gcp-key.json \
  --iam-account=n8n-deployer@PROJECT_ID.iam.gserviceaccount.com

# Authenticate with service account
gcloud auth activate-service-account \
  --key-file=~/gcp-key.json

# Set as application default credentials for Terraform
export GOOGLE_APPLICATION_CREDENTIALS=~/gcp-key.json
```

**Security Note**: Never commit service account keys to version control. Add to `.gitignore`:
```bash
echo "gcp-key.json" >> .gitignore
echo "*.json" >> .gitignore  # If not already present
```

### 2. Configure Default Settings

```bash
# Set default project
gcloud config set project PROJECT_ID

# Set default region
gcloud config set compute/region us-central1

# Set default zone
gcloud config set compute/zone us-central1-a

# Verify configuration
gcloud config list
```

### 3. Enable Billing

```bash
# List billing accounts
gcloud billing accounts list

# Link billing account to project
gcloud billing projects link PROJECT_ID \
  --billing-account=BILLING_ACCOUNT_ID

# Verify billing is enabled
gcloud billing projects describe PROJECT_ID
```

## IAM Permissions

### Philosophy: Least Privilege (Learned from Azure)

Based on Azure's highly scoped permissions (Network Contributor + Key Vault Secrets User), we aim for minimal, targeted permissions.

### Minimum Required Roles

For deploying n8n on GKE, the user or service account needs the following IAM roles:

#### Option 1: Pre-Defined Roles (Easier, Slightly Over-Permissioned)

**Core Infrastructure Roles:**

```bash
# Networking - For VPC, subnets, Cloud NAT, firewall rules, external IPs
roles/compute.networkAdmin           # Create/manage networks, subnets, NAT, IPs

# GKE Management - For cluster and node pool operations
roles/container.clusterAdmin         # Create/manage GKE clusters (NOT container.admin)

# Service Account Management - For creating/using service accounts
roles/iam.serviceAccountUser         # Use service accounts
roles/iam.serviceAccountAdmin        # Create/delete service accounts (scoped)

# Secret Management - For storing encryption keys and credentials
roles/secretmanager.secretAccessor   # Read secrets (was: secretmanager.admin ❌)
roles/secretmanager.admin            # Only if creating secrets via Terraform
```

**Optional Roles (Based on Configuration):**

```bash
# Cloud SQL Admin - ONLY if using Cloud SQL PostgreSQL
roles/cloudsql.admin

# DNS Admin - ONLY if using Cloud DNS (NOT needed for Let's Encrypt HTTP-01)
# roles/dns.admin  # ❌ NOT REQUIRED for default setup
```

**❌ AVOID THESE OVERLY BROAD ROLES:**

```bash
# roles/resourcemanager.projectIamAdmin  # ❌ TOO BROAD - grants ALL IAM permissions
# roles/owner                             # ❌ TOO BROAD - full project access
# roles/editor                            # ❌ TOO BROAD - can modify everything
```

#### Option 2: Custom Role (Recommended for Production)

### Assigning Roles

#### For User Account

```bash
# Get current user email
USER_EMAIL=$(gcloud config get-value account)

# Assign roles
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/compute.networkAdmin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/container.admin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/iam.serviceAccountAdmin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/secretmanager.admin"

# For PostgreSQL deployments
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="roles/cloudsql.admin"
```

#### For Service Account

```bash
# Service account email
SA_EMAIL=n8n-deployer@PROJECT_ID.iam.gserviceaccount.com

# Assign roles
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/compute.networkAdmin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/container.admin"

# Continue for other roles...
```

### Verify Permissions

```bash
# List your current IAM policy
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --format="table(bindings.role)" \
  --filter="bindings.members:$USER_EMAIL"

# Test specific permissions
gcloud iam test-iam-permissions PROJECT_ID \
  --permissions=container.clusters.create,compute.networks.create
```

Create a custom role with only the permissions needed for n8n deployment:

```bash
# Create custom role definition
cat > n8n-deployer-role.yaml <<EOF
title: "N8N GKE Deployer"
description: "Minimal permissions for deploying n8n on GKE (validated against AWS/Azure)"
stage: "GA"
includedPermissions:
  # VPC & Networking (equivalent to AWS VPC permissions)
  - compute.networks.create
  - compute.networks.delete
  - compute.networks.get
  - compute.networks.update
  - compute.networks.updatePolicy
  - compute.subnetworks.create
  - compute.subnetworks.delete
  - compute.subnetworks.get
  - compute.subnetworks.update
  - compute.subnetworks.use                    # Required for GKE node placement
  - compute.subnetworks.useExternalIp          # Required for external IPs

  # External IPs (equivalent to AWS Elastic IPs)
  - compute.addresses.create
  - compute.addresses.delete
  - compute.addresses.get
  - compute.addresses.list
  - compute.addresses.use                      # Critical for LoadBalancer

  # Cloud NAT (equivalent to AWS NAT Gateway)
  - compute.routers.create
  - compute.routers.delete
  - compute.routers.get
  - compute.routers.update
  - compute.routers.use

  # Firewall Rules (equivalent to AWS Security Groups)
  - compute.firewalls.create
  - compute.firewalls.delete
  - compute.firewalls.get
  - compute.firewalls.list
  - compute.firewalls.update

  # Load Balancers (equivalent to AWS ELB/NLB)
  - compute.backendServices.create
  - compute.backendServices.delete
  - compute.backendServices.get
  - compute.backendServices.use
  - compute.targetPools.create
  - compute.targetPools.delete
  - compute.targetPools.get
  - compute.targetPools.use
  - compute.forwardingRules.create
  - compute.forwardingRules.delete
  - compute.forwardingRules.get

  # GKE Cluster Management (equivalent to AWS EKS permissions)
  - container.clusters.create
  - container.clusters.delete
  - container.clusters.get
  - container.clusters.update
  - container.operations.get
  - container.operations.list

  # GKE Node Pools (equivalent to AWS EKS node groups)
  - container.nodePools.create
  - container.nodePools.delete
  - container.nodePools.get
  - container.nodePools.update

  # Compute Instances (for node visibility)
  - compute.instances.get
  - compute.instances.list

  # Service Accounts (equivalent to AWS IAM roles)
  - iam.serviceAccounts.create
  - iam.serviceAccounts.delete
  - iam.serviceAccounts.get
  - iam.serviceAccounts.list
  - iam.serviceAccounts.actAs                  # Use service accounts
  - iam.serviceAccounts.getIamPolicy           # View SA permissions
  - iam.serviceAccounts.setIamPolicy           # Bind Workload Identity

  # Secret Manager (equivalent to AWS Secrets Manager)
  - secretmanager.secrets.create
  - secretmanager.secrets.delete
  - secretmanager.secrets.get
  - secretmanager.secrets.list
  - secretmanager.versions.add
  - secretmanager.versions.access
  - secretmanager.versions.destroy

  # Persistent Disks (equivalent to AWS EBS)
  - compute.disks.create
  - compute.disks.delete
  - compute.disks.get
  - compute.disks.use

  # Cloud SQL (optional - only if using PostgreSQL, equivalent to AWS RDS)
  # Uncomment if using Cloud SQL:
  # - cloudsql.instances.create
  # - cloudsql.instances.delete
  # - cloudsql.instances.get
  # - cloudsql.instances.update
  # - cloudsql.instances.connect
  # - cloudsql.users.create
  # - cloudsql.users.delete
  # - cloudsql.databases.create
EOF

# Create the custom role
gcloud iam roles create n8nGkeDeployer \
  --project=PROJECT_ID \
  --file=n8n-deployer-role.yaml

# Assign custom role
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:$USER_EMAIL" \
  --role="projects/PROJECT_ID/roles/n8nGkeDeployer"
```

## Required APIs

### Enable All Required APIs

```bash
# Core GCP APIs
gcloud services enable compute.googleapis.com              # Compute Engine
gcloud services enable container.googleapis.com            # GKE
gcloud services enable cloudresourcemanager.googleapis.com # Resource Manager
gcloud services enable iam.googleapis.com                  # IAM
gcloud services enable iamcredentials.googleapis.com       # IAM Credentials

# Storage & Secrets
gcloud services enable secretmanager.googleapis.com        # Secret Manager

# Database (if using Cloud SQL)
gcloud services enable sqladmin.googleapis.com             # Cloud SQL

# Networking (optional but recommended)
gcloud services enable dns.googleapis.com                  # Cloud DNS
gcloud services enable servicenetworking.googleapis.com    # Service Networking

# Monitoring & Logging (optional but recommended)
gcloud services enable logging.googleapis.com              # Cloud Logging
gcloud services enable monitoring.googleapis.com           # Cloud Monitoring
```

### Enable All at Once

```bash
# Enable all APIs in one command
gcloud services enable \
  compute.googleapis.com \
  container.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  dns.googleapis.com \
  servicenetworking.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com
```

### Verify APIs are Enabled

```bash
# List all enabled services
gcloud services list --enabled

# Check specific API
gcloud services list --enabled --filter="name:container.googleapis.com"
```

## Service Account Roles

### Understanding GKE Service Accounts (Similar to AWS/Azure Identity Model)

GKE uses **3 different service accounts**, similar to how Azure AKS uses 3 separate managed identities and AWS EKS uses separate IAM roles.

#### 1. GKE Cluster Service Account

**Purpose**: Used by the GKE control plane to manage cluster infrastructure.

**AWS Equivalent**: EKS Cluster IAM Role
**Azure Equivalent**: AKS Cluster Identity

**Required Permissions:**
```bash
# Option A: Use default Compute Engine service account (not recommended for production)
PROJECT_NUMBER-compute@developer.gserviceaccount.com

# Option B: Create custom cluster service account (recommended)
gcloud iam service-accounts create gke-cluster-sa \
  --display-name="GKE Cluster Service Account"

# Assign minimal permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:gke-cluster-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/container.serviceAgent"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:gke-cluster-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/compute.networkUser"
```

#### 2. GKE Node Pool Service Account

**Purpose**: Used by worker nodes to pull images, write logs, push metrics.

**AWS Equivalent**: EKS Node Group IAM Role
**Azure Equivalent**: AKS Kubelet Identity

**Required Permissions:**
```bash
# Create node pool service account
gcloud iam service-accounts create gke-nodes-sa \
  --display-name="GKE Node Pool Service Account"

# Assign permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:gke-nodes-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:gke-nodes-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:gke-nodes-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"  # For pulling container images
```

#### 3. Workload Service Account (for n8n Pods)

**Purpose**: Used by n8n application pods to access GCP services (Secret Manager, Cloud SQL, etc.).

**AWS Equivalent**: IRSA (IAM Roles for Service Accounts)
**Azure Equivalent**: Workload Identity / Secrets Provider Identity

**Required Permissions:**
```bash
# Create workload service account
gcloud iam service-accounts create n8n-workload-sa \
  --display-name="N8N Workload Service Account"

# Grant Secret Manager access (equivalent to Azure Key Vault Secrets User)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:n8n-workload-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Grant Cloud SQL access (if using PostgreSQL)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:n8n-workload-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

## Workload Identity Configuration

### GKE Workload Identity Setup

Workload Identity allows GKE Pods to access GCP services securely without service account keys.

**This is equivalent to:**
- AWS: IRSA (IAM Roles for Service Accounts)
- Azure: Workload Identity with Managed Identity binding

#### 1. Create Google Service Account (GSA)

```bash
# Create service account for n8n workload
gcloud iam service-accounts create n8n-workload \
  --display-name="N8N Workload Service Account" \
  --project=PROJECT_ID

# Grant necessary permissions (example: Secret Manager access)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:n8n-workload@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

#### 2. Enable Workload Identity on GKE Cluster

```bash
# During cluster creation (Terraform handles this)
gcloud container clusters create CLUSTER_NAME \
  --workload-pool=PROJECT_ID.svc.id.goog \
  --region=us-central1
```

#### 3. Bind Kubernetes Service Account to GSA

```bash
# After cluster creation and n8n deployment

# Create Kubernetes service account (if not exists)
kubectl create serviceaccount n8n-sa -n n8n

# Bind GSA to KSA
gcloud iam service-accounts add-iam-policy-binding \
  n8n-workload@PROJECT_ID.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:PROJECT_ID.svc.id.goog[n8n/n8n-sa]"

# Annotate Kubernetes service account
kubectl annotate serviceaccount n8n-sa \
  -n n8n \
  iam.gke.io/gcp-service-account=n8n-workload@PROJECT_ID.iam.gserviceaccount.com
```

## Cost Estimates

### Monthly Cost Breakdown (us-central1)

Based on minimal production configuration with SQLite storage.

**⚠️ Cost Estimates Corrected Based on Actual GCP Pricing (October 2025)**

| Component | Specification | Monthly Cost (USD) | Notes |
|-----------|--------------|-------------------|-------|
| **GKE Control Plane** | Regional cluster (3 zones) | $73.00 | Fixed cost, cannot be reduced |
| **Compute Nodes** | 1x e2-medium (2 vCPU, 4GB RAM) | $24.27 | With sustained use discount |
| **Persistent Disk** | 100GB pd-balanced (regional) | $10.00 | Regional disk for HA (was $4 ❌) |
| **Cloud NAT** | 1 NAT Gateway | $32.85 | $0.045/hr + data processing |
| **Load Balancer** | HTTP(S) LB + static IP | $18.26 | Forwarding rule + static IP |
| **Egress Traffic** | ~20GB/month | $2.40 | $0.12/GB (first 1TB) |
| **Cloud Operations** | Basic logging/monitoring | $8.00 | Logs + metrics ingestion |
| **Total (SQLite)** | | **~$168.78** | Corrected from $135 ❌ |

**With Cloud SQL PostgreSQL** (db-f1-micro shared CPU):
| Component | Monthly Cost (USD) | Notes |
|-----------|-------------------|-------|
| Base configuration | $168.78 | |
| Cloud SQL (db-f1-micro) | +$26.28 | Shared-core instance |
| Cloud SQL Storage (100GB) | +$17.00 | SSD storage |
| **Total (PostgreSQL)** | **~$212.06** | Corrected from $165 ❌ |

### Cost Optimization Strategies

#### 1. Sustained Use Discounts (Automatic)

GCP automatically applies sustained use discounts:
- 20% discount for resources used 50-100% of the month
- 30% discount for resources used 75-100% of the month
- **Potential savings**: $5-10/month on compute

#### 2. Committed Use Discounts

For long-term deployments (1 or 3 years):

```bash
# View available commitments
gcloud compute commitments list

# Create 1-year commitment for e2-medium
gcloud compute commitments create n8n-commitment \
  --resources=vcpu=2,memory=4GB \
  --plan=12-month \
  --region=us-central1
```

**Savings**: Up to 57% on compute costs = ~$14/month savings

#### 3. Preemptible Nodes (Not Recommended for Production)

```bash
# Preemptible nodes are 70-80% cheaper
# Cost: ~$5/month vs ~$25/month
# Trade-off: Nodes can be terminated with 30 seconds notice
```

**Only suitable for**:
- Development environments
- Fault-tolerant batch workloads
- **Not recommended** for n8n production due to workflow interruptions

#### 4. Regional vs Multi-Regional Resources

| Region | Relative Cost | Latency (US East) |
|--------|--------------|-------------------|
| us-central1 (Iowa) | Baseline | ~30ms |
| us-east1 (S. Carolina) | +0% | ~10ms |
| us-west1 (Oregon) | +0% | ~70ms |
| europe-west1 (Belgium) | +5% | ~100ms |
| asia-southeast1 (Singapore) | +10-15% | ~250ms |

**Recommendation**: Use `us-central1` for best cost, `us-east1` for East Coast proximity

#### 5. Storage Cost Comparison

| Disk Type | IOPS | Cost (100GB) | Use Case |
|-----------|------|--------------|----------|
| pd-standard | 600 | $4.00 | Light workloads |
| pd-balanced | 3,000 | $4.00 | **Recommended** |
| pd-ssd | 30,000 | $17.00 | High I/O workloads |

**Recommendation**: Use `pd-balanced` for best price/performance ratio

### Cost Comparison Summary

**⚠️ Corrected October 2025 Pricing**

| Cloud Provider | Monthly Cost (SQLite) | Monthly Cost (PostgreSQL) | Control Plane Cost |
|----------------|---------------------|--------------------------|-------------------|
| **Azure (East US)** | **$81** | **$96** | **FREE** ✅ |
| **AWS (us-east-1)** | **$157** | **$172** | $73/month |
| **GCP (us-central1)** | **$169** | **$212** | $73/month |

**Key Insights:**
1. **Azure is cheapest**: Free AKS control plane saves $73/month vs AWS/GCP
2. **GCP is most expensive**: Higher Cloud NAT costs ($33 vs $9 estimate) + regional disk costs
3. **GCP Cloud SQL is expensive**: $43/month (instance + storage) vs AWS RDS $15-30/month
4. **AWS middle ground**: Control plane cost, but cheaper managed services than GCP

**When to Choose GCP:**
- ✅ Already using Google Workspace / Google services ecosystem
- ✅ Need Workload Identity (better than AWS IRSA implementation)
- ✅ Advanced GKE features (Binary Authorization, Config Sync, etc.)
- ❌ **NOT for cost optimization** - Azure is 52% cheaper for this workload

## Architecture Overview

### What Gets Deployed

#### Infrastructure Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Google Cloud Platform                     │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              VPC Network (10.0.0.0/16)                 │ │
│  │                                                         │ │
│  │  ┌──────────────────┐      ┌──────────────────┐       │ │
│  │  │  Public Subnet   │      │  Private Subnet  │       │ │
│  │  │  (10.0.1.0/24)   │      │  (10.0.2.0/24)   │       │ │
│  │  │                  │      │                  │       │ │
│  │  │  • Cloud NAT     │      │  • GKE Nodes     │       │ │
│  │  │  • Load Balancer │      │  • n8n Pods      │       │ │
│  │  └──────────────────┘      └──────────────────┘       │ │
│  │                                                         │ │
│  │         ┌────────────────────────────────┐             │ │
│  │         │    GKE Cluster (Regional)      │             │ │
│  │         │  • Kubernetes 1.28+            │             │ │
│  │         │  • Workload Identity enabled   │             │ │
│  │         │  • VPC-native networking       │             │ │
│  │         └────────────────────────────────┘             │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Secret Manager │  │ Cloud SQL    │  │ Persistent     │  │
│  │ • Encryption   │  │ • PostgreSQL │  │ Disks (100GB)  │  │
│  │   Keys         │  │   (Optional) │  │ • pd-balanced  │  │
│  └────────────────┘  └──────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### Kubernetes Resources

- **Namespace**: `n8n`
- **Deployment**: n8n application with 1 replica
- **Service**: ClusterIP for internal communication
- **Ingress**: nginx-ingress-controller with HTTP(S) routing
- **PersistentVolumeClaim**: 100GB for workflow data
- **Secret**: Database credentials (if using Cloud SQL)
- **ConfigMap**: n8n configuration

### GCP Service Mappings

| AWS Service | Azure Service | **GCP Service** | Purpose |
|-------------|---------------|-----------------|---------|
| VPC | Virtual Network | **VPC Network** | Network isolation |
| Subnet | Subnet | **Subnet** | Network segmentation |
| NAT Gateway | NAT Gateway | **Cloud NAT** | Outbound internet access |
| EKS | AKS | **GKE** | Managed Kubernetes |
| EBS | Azure Disk | **Persistent Disk** | Block storage |
| RDS PostgreSQL | Azure Database | **Cloud SQL** | Managed PostgreSQL |
| SSM Parameter Store | Key Vault | **Secret Manager** | Secrets storage |
| Secrets Manager | Key Vault | **Secret Manager** | Credentials management |
| ELB/NLB | Load Balancer | **Cloud Load Balancing** | Traffic distribution |
| Elastic IP | Public IP | **Static External IP** | Fixed IP address |
| IAM Roles | Managed Identity | **Service Accounts** | Resource authentication |
| CloudWatch | Azure Monitor | **Cloud Operations** | Monitoring & logging |

## Critical Permissions (Lessons from Azure/AWS)

### LoadBalancer Creation Permission (Equivalent to Azure's Network Contributor)

**Azure Lesson Learned:** Azure LoadBalancer failed with `LinkedAuthorizationFailed` error because the AKS cluster identity lacked `Microsoft.Network/virtualNetworks/subnets/join/action` permission.

**GCP Equivalent Issue:** GKE cluster service account needs permission to:
1. Create Load Balancer backend services
2. Create forwarding rules
3. **Use external IP addresses**
4. **Attach load balancer to VPC subnets**

**Solution:**
```bash
# Ensure GKE cluster service account has these permissions:
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:gke-cluster-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/compute.loadBalancerAdmin"

# OR for custom role, ensure these are included:
# - compute.addresses.use
# - compute.backendServices.create
# - compute.backendServices.use
# - compute.forwardingRules.create
# - compute.targetPools.create
# - compute.targetPools.use
```

**Symptoms if missing:**
- LoadBalancer service stuck in `<pending>` status forever
- Events show: "Error syncing load balancer: failed to ensure load balancer"
- Error: "Required permission compute.addresses.use on resource"

### Secret Manager Access (Equivalent to Azure Key Vault)

**Azure Lesson Learned:** Azure requires separate "Key Vault Secrets User" role (read-only) for secrets access, NOT "Key Vault Admin".

**GCP Equivalent:**
```bash
# ❌ AVOID: roles/secretmanager.admin (can delete secrets)
# ✅ USE: roles/secretmanager.secretAccessor (read-only)

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:n8n-workload-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Cloud SQL Private IP Connectivity

**AWS Lesson Learned:** RDS required security group rules from both EKS cluster SG AND node SG for connectivity.

**GCP Equivalent:** Cloud SQL with private IP requires:
1. VPC peering with `servicenetworking.googleapis.com`
2. Firewall rules allowing traffic from GKE node pools
3. Cloud SQL Proxy OR private service connection

**Solution:**
```bash
# Reserve IP range for Cloud SQL
gcloud compute addresses create google-managed-services-default \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network=VPC_NAME

# Create VPC peering
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-default \
  --network=VPC_NAME

# Verify peering
gcloud services vpc-peerings list --network=VPC_NAME
```

**Alternative (Easier):** Use Cloud SQL Proxy sidecar container:
```yaml
containers:
- name: cloud-sql-proxy
  image: gcr.io/cloudsql-docker/gce-proxy:latest
  command:
    - "/cloud_sql_proxy"
    - "-instances=PROJECT_ID:REGION:INSTANCE=tcp:5432"
```

## Common Pitfalls

### 1. VPC-Native Clusters and IP Exhaustion

**Problem**: GKE VPC-native clusters use alias IP ranges for Pods and Services. Improper planning can lead to IP exhaustion.

**Solution**:
```bash
# Ensure adequate IP ranges in Terraform configuration
# Primary range: 10.0.0.0/20 (4,096 IPs for nodes)
# Secondary range for Pods: 10.4.0.0/14 (262,144 IPs)
# Secondary range for Services: 10.0.16.0/20 (4,096 IPs)
```

**Prevention**:
- Use `/14` or larger for Pod IP range
- Use `/20` for Services
- Monitor IP utilization: `gcloud container clusters describe CLUSTER_NAME`

### 2. Workload Identity Misconfiguration

**Problem**: Pods cannot access GCP services due to incorrect Workload Identity binding.

**Solution**:
```bash
# Verify binding
gcloud iam service-accounts get-iam-policy \
  n8n-workload@PROJECT_ID.iam.gserviceaccount.com

# Check annotation
kubectl describe sa n8n-sa -n n8n | grep Annotations
```

### 3. Cloud SQL Connectivity Issues

**Problem**: Pods cannot connect to Cloud SQL instance.

**Solutions**:

**Option A: Cloud SQL Proxy (Recommended)**
```yaml
# Add Cloud SQL Proxy sidecar to n8n deployment
- name: cloud-sql-proxy
  image: gcr.io/cloudsql-docker/gce-proxy:latest
  command:
    - "/cloud_sql_proxy"
    - "-instances=PROJECT_ID:REGION:INSTANCE_NAME=tcp:5432"
```

**Option B: Private IP**
```bash
# Enable Private IP for Cloud SQL
gcloud sql instances patch INSTANCE_NAME \
  --network=projects/PROJECT_ID/global/networks/VPC_NAME \
  --no-assign-ip

# Configure VPC Peering for Cloud SQL
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=RESERVED_RANGE_NAME \
  --network=VPC_NAME
```

### 4. Ingress Controller Choice

**Problem**: Confusion between GCE Ingress and nginx-ingress-controller.

**Comparison**:

| Feature | GCE Ingress | nginx-ingress |
|---------|-------------|---------------|
| Integration | Native GCP | Third-party |
| Cost | Moderate | Lower |
| Features | Basic | Advanced |
| SSL/TLS | Google-managed | cert-manager |
| Custom config | Limited | Extensive |

**Recommendation**: Use **nginx-ingress-controller** for:
- Let's Encrypt integration
- Advanced routing rules
- Consistency with AWS/Azure deployments

### 5. Persistent Disk Performance

**Problem**: Slow I/O performance for n8n workflows.

**Solution**:
```bash
# Use pd-balanced (default) for most workloads
# Upgrade to pd-ssd if experiencing slowness

# Check disk performance
kubectl describe pvc n8n-data -n n8n

# Monitor IOPS
gcloud compute disks describe DISK_NAME --zone=ZONE
```

### 6. Load Balancer Costs

**Problem**: Unexpected high costs from load balancer.

**Causes**:
- External HTTP(S) Load Balancer: $18/month base + data transfer
- Multiple forwarding rules: $10 each
- High egress traffic: $0.12/GB

**Optimization**:
```bash
# Use single Ingress for multiple services
# Consolidate routing rules
# Monitor egress: gcloud compute forwarding-rules list
```

### 7. GKE Control Plane Costs

**Problem**: $73/month for regional GKE cluster seems high.

**Context**:
- GKE Standard: $0.10/hour per cluster = $73/month
- Zonal cluster: Free control plane but single-zone (not recommended for production)
- GKE Autopilot: Pay-per-Pod model, may be cheaper for small workloads

**Decision**:
- **Production**: Regional cluster for HA ($73/month)
- **Development**: Zonal cluster (free control plane)
- **Very small workloads**: Consider GKE Autopilot

### 8. API Enablement Delays

**Problem**: Terraform fails with "API not enabled" errors.

**Solution**:
```bash
# Enable APIs before running Terraform
gcloud services enable container.googleapis.com
gcloud services enable compute.googleapis.com

# APIs can take 2-5 minutes to fully activate
# Wait before running terraform apply
```

### 9. Terraform State Management

**Problem**: Concurrent Terraform runs cause state corruption.

**Solution**:
```hcl
# Use GCS backend with state locking
terraform {
  backend "gcs" {
    bucket = "PROJECT_ID-terraform-state"
    prefix = "n8n-gke"
  }
}
```

```bash
# Create state bucket
gsutil mb -p PROJECT_ID -l us-central1 gs://PROJECT_ID-terraform-state

# Enable versioning
gsutil versioning set on gs://PROJECT_ID-terraform-state
```

### 10. Certificate Management with cert-manager

**Problem**: Let's Encrypt certificate issuance fails.

**Common Causes**:
1. DNS not propagated (wait 5-10 minutes)
2. HTTP-01 challenge blocked by firewall
3. Rate limits exceeded (use staging first)

**Solution**:
```bash
# Use Let's Encrypt staging for testing
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: YOUR_EMAIL
    privateKeySecretRef:
      name: letsencrypt-staging
    solvers:
    - http01:
        ingress:
          class: nginx
EOF

# Debug certificate issues
kubectl describe certificate -n n8n
kubectl describe challenge -n n8n
kubectl logs -n cert-manager deployment/cert-manager
```

## Troubleshooting

### Permission Errors

#### Error: "Permission denied" or "403 Forbidden"

```bash
# Verify current account
gcloud auth list

# Check project
gcloud config get-value project

# List IAM roles
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:$(gcloud config get-value account)"

# Test specific permission
gcloud iam test-iam-permissions PROJECT_ID \
  --permissions=container.clusters.create
```

**Fix**: Add missing roles (see [IAM Permissions](#iam-permissions))

#### Error: "API not enabled"

```bash
# Check if API is enabled
gcloud services list --enabled | grep container

# Enable missing API
gcloud services enable container.googleapis.com

# Wait 2-5 minutes for activation
```

### Cluster Access Issues

#### Error: "Unable to connect to the server"

```bash
# Update kubeconfig
gcloud container clusters get-credentials CLUSTER_NAME \
  --region=REGION \
  --project=PROJECT_ID

# Verify kubectl context
kubectl config current-context

# Test connection
kubectl get nodes
```

#### Error: "Unauthorized" when accessing cluster

```bash
# Ensure you have container.clusters.get permission
gcloud container clusters describe CLUSTER_NAME \
  --region=REGION

# If using service account, verify role binding
kubectl get clusterrolebinding -o yaml | grep -A5 "$(gcloud config get-value account)"
```

### Deployment Failures

#### Pods in CrashLoopBackOff

```bash
# Check pod logs
kubectl logs -n n8n deployment/n8n --tail=100

# Describe pod
kubectl describe pod -n n8n -l app=n8n

# Common causes:
# 1. Database connection failure (check credentials)
# 2. Persistent volume mount issues
# 3. Insufficient resources (check node capacity)
```

#### PersistentVolumeClaim Pending

```bash
# Check PVC status
kubectl describe pvc n8n-data -n n8n

# Verify storage class exists
kubectl get storageclass

# Common issues:
# 1. No default storage class
# 2. Insufficient disk quota
# 3. Zone mismatch (PVC in different zone than node)

# Fix: Create storage class
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: pd-balanced
provisioner: pd.csi.storage.gke.io
parameters:
  type: pd-balanced
  replication-type: regional-pd
volumeBindingMode: WaitForFirstConsumer
EOF
```

### Networking Issues

#### LoadBalancer Service Stuck in Pending

```bash
# Check service
kubectl describe svc -n ingress-nginx ingress-nginx-controller

# Verify external IP allocation
gcloud compute addresses list

# Common causes:
# 1. Quota exceeded for external IPs
# 2. Insufficient permissions for load balancer creation
# 3. Firewall rules blocking health checks

# Check quotas
gcloud compute project-info describe --project=PROJECT_ID | grep -A5 EXTERNAL_ADDRESSES
```

#### Cannot Access Application via LoadBalancer IP

```bash
# Get external IP
EXTERNAL_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test connectivity
curl -I http://$EXTERNAL_IP

# Check firewall rules
gcloud compute firewall-rules list | grep allow

# Verify health check
gcloud compute backend-services list
```

### Cost Monitoring

#### Unexpected High Costs

```bash
# View billing
gcloud billing accounts list
gcloud billing projects describe PROJECT_ID

# Check resource usage
gcloud compute instances list
gcloud compute disks list
gcloud sql instances list

# Common cost drivers:
# 1. Idle resources (delete unused VMs, disks)
# 2. Egress traffic (review data transfer)
# 3. Load balancer charges (consolidate rules)
# 4. Persistent disks (snapshot and delete unused)
```

#### Cost Optimization Commands

```bash
# List all compute instances
gcloud compute instances list --format="table(name,zone,machineType,status,creationTimestamp)"

# Find unused persistent disks
gcloud compute disks list --filter="users:*" --format="table(name,zone,sizeGb,status)"

# Check committed use discounts
gcloud compute commitments list

# Review sustained use discounts
# Automatically applied - check billing reports
```

### Logging and Monitoring

#### Enable Cloud Operations

```bash
# Enable Cloud Logging and Monitoring
gcloud services enable logging.googleapis.com
gcloud services enable monitoring.googleapis.com

# View GKE cluster logs
gcloud logging read "resource.type=k8s_cluster AND resource.labels.cluster_name=CLUSTER_NAME" \
  --limit 50 \
  --format json

# View n8n application logs
kubectl logs -n n8n deployment/n8n --tail=100 -f
```

#### Create Alerts

```bash
# Create uptime check
gcloud monitoring uptime create UPTIME_CHECK_NAME \
  --resource-type=uptime-url \
  --display-name="N8N Uptime Check" \
  --http-check-path="/" \
  --port=443 \
  --check-interval=300 \
  --monitored-resource="https://your-n8n-domain.com"
```

### Support Resources

- **GCP Documentation**: https://cloud.google.com/kubernetes-engine/docs
- **GKE Best Practices**: https://cloud.google.com/kubernetes-engine/docs/best-practices
- **Terraform GCP Provider**: https://registry.terraform.io/providers/hashicorp/google/latest/docs
- **GKE Pricing Calculator**: https://cloud.google.com/products/calculator
- **GCP Status Dashboard**: https://status.cloud.google.com/

## Implementation Requirements for setup.py

### Overview

To add GCP as a third cloud provider option (alongside AWS and Azure), the following components need to be implemented based on the successful AWS/Azure deployment patterns.

### Required Code Changes

#### 1. GCP Configuration Class

**File**: `setup.py`
**Location**: After `AzureDeploymentConfig` class (around line 275)

**Requirements**:
```python
class GCPDeploymentConfig:
    """Stores all configuration for GCP GKE deployment"""

    # GCP-specific settings
    gcp_project_id: str          # GCP project ID
    gcp_region: str              # e.g., us-central1
    gcp_zone: str                # e.g., us-central1-a

    # Cluster settings
    cluster_name: str            # GKE cluster name
    node_machine_type: str       # e.g., e2-medium
    node_count: int              # Number of nodes (min 1)

    # Network settings
    vpc_name: str                # VPC network name
    subnet_name: str             # Subnet name

    # Database settings (matches AWS/Azure pattern)
    database_type: str           # "sqlite" or "cloudsql"
    cloudsql_instance_name: str  # Optional Cloud SQL instance
    cloudsql_tier: str           # e.g., db-f1-micro

    # Application settings
    n8n_namespace: str           # Kubernetes namespace
    n8n_host: str                # Domain name
    n8n_encryption_key: str      # Generated encryption key

    # TLS settings (matches AWS/Azure pattern)
    enable_tls: bool
    tls_provider: str            # "letsencrypt" or "custom"
    letsencrypt_email: str

    # Basic auth settings (matches AWS/Azure pattern)
    enable_basic_auth: bool
    basic_auth_username: str
    basic_auth_password: str
```

**GCP-Specific Mapping**:
| AWS | Azure | GCP |
|-----|-------|-----|
| `aws_profile` | `azure_subscription_id` | `gcp_project_id` |
| `aws_region` | `azure_location` | `gcp_region` + `gcp_zone` |
| `eks_cluster_name` | `cluster_name` | `cluster_name` |
| `node_instance_type` | `node_size` | `node_machine_type` |
| RDS | Azure PostgreSQL | Cloud SQL |

#### 2. GCP Authentication Checker

**File**: `setup.py`
**Location**: After `AWSAuthChecker` class (around line 640)

**Requirements**:
```python
class GCPAuthChecker:
    """Handles GCP authentication verification"""

    @staticmethod
    def list_projects() -> list:
        """Get list of accessible GCP projects"""
        # Run: gcloud projects list --format=json
        # Parse JSON output
        # Return list of project IDs

    @staticmethod
    def verify_credentials(project_id: str) -> Tuple[bool, str]:
        """Verify GCP credentials work for specified project"""
        # Run: gcloud auth list
        # Run: gcloud config set project {project_id}
        # Run: gcloud projects describe {project_id}
        # Return (success: bool, message: str)

    @staticmethod
    def check_required_apis(project_id: str) -> Tuple[bool, list]:
        """Check if required GCP APIs are enabled"""
        required_apis = [
            'compute.googleapis.com',
            'container.googleapis.com',
            'secretmanager.googleapis.com',
            'sqladmin.googleapis.com',  # if using Cloud SQL
        ]
        # Run: gcloud services list --enabled --project={project_id}
        # Return (all_enabled: bool, missing_apis: list)
```

**Critical Implementation Notes**:
- Similar to `AWSAuthChecker.verify_credentials()` (line 606)
- Must handle timeout scenarios (like AWS 30-second timeout)
- Should detect if user is authenticated via `gcloud auth login` or service account

#### 3. GCP Configuration Prompts

**File**: `setup.py`
**Location**: In `ConfigurationPrompt` class, add `collect_gcp_configuration()` method

**Requirements**:
```python
def collect_gcp_configuration(self, skip_tls: bool = False) -> GCPDeploymentConfig:
    """Collect GCP-specific configuration from user (interactive prompts)"""

    # Similar to collect_azure_configuration() (line 3850)

    # 1. GCP Project Selection
    #    - List available projects using gcloud
    #    - Prompt user to select project
    #    - Verify access to selected project

    # 2. Region/Zone Selection
    #    - Default: us-central1 / us-central1-a
    #    - Options: us-east1, us-west1, europe-west1, asia-southeast1

    # 3. Cluster Configuration
    #    - Cluster name (default: n8n-gke-cluster)
    #    - Node machine type (default: e2-medium)
    #    - Node count (default: 1, min: 1, max: 5)

    # 4. Database Selection (MATCHES AWS PATTERN)
    #    - SQLite (default, simpler)
    #    - Cloud SQL PostgreSQL (production)
    #    - If Cloud SQL: instance name, tier (db-f1-micro)

    # 5. Domain Configuration
    #    - n8n hostname (e.g., n8n-gcp.example.com)

    # 6. TLS Configuration (if not skip_tls)
    #    - Enable TLS? (yes/no)
    #    - Provider: Let's Encrypt or Custom
    #    - Email for Let's Encrypt

    # 7. Basic Auth (if not skip_tls)
    #    - Enable basic auth? (yes/no)
    #    - Username/password
```

**Pattern to Follow**: AWS config collection (line 3883-3885), Azure config collection (line 3848-3850)

#### 4. GCP Terraform Integration

**File**: `setup.py`
**Location**: New function `deploy_gcp_terraform()`

**Requirements**:
```python
def deploy_gcp_terraform(config: GCPDeploymentConfig, terraform_dir: Path) -> bool:
    """Deploy GCP infrastructure using Terraform"""

    # Similar to deploy_azure_terraform() (around line 3861)

    # 1. Initialize Terraform
    #    tf_runner = TerraformRunner(terraform_dir)
    #    tf_runner.init()

    # 2. Create terraform.tfvars with GCP config
    #    - project_id = config.gcp_project_id
    #    - region = config.gcp_region
    #    - zone = config.gcp_zone
    #    - cluster_name = config.cluster_name
    #    - etc.

    # 3. Run terraform plan

    # 4. Confirm with user

    # 5. Run terraform apply
    #    Creates:
    #    - VPC network
    #    - Subnets (public/private)
    #    - Cloud NAT
    #    - GKE cluster
    #    - Node pools
    #    - Service accounts
    #    - Secret Manager secrets
    #    - Cloud SQL (optional)

    # 6. Configure kubectl
    #    gcloud container clusters get-credentials {cluster_name} \
    #      --region={region} --project={project_id}

    # 7. Return success/failure
```

**Terraform Outputs Required** (similar to AWS outputs, line 3962):
- `configure_kubectl`: gcloud command to configure kubectl
- `n8n_encryption_key_value`: from Secret Manager
- `database_type`: "sqlite" or "cloudsql"
- `cloudsql_connection_name`: if using Cloud SQL
- `cloudsql_database_name`: if using Cloud SQL
- `cloudsql_username`: if using Cloud SQL
- `cloudsql_password`: if using Cloud SQL

#### 5. GCP Helm Deployment

**File**: `setup.py`
**Location**: New function `deploy_gcp_helm()`

**Requirements**:
```python
def deploy_gcp_helm(config: GCPDeploymentConfig, charts_dir: Path, encryption_key: str) -> bool:
    """Deploy n8n on GKE using Helm"""

    # Similar to deploy_azure_helm() (around line 3866)

    # 1. Prepare database configuration
    #    db_config = {
    #        'database_type': 'sqlite' or 'cloudsql',
    #        'cloudsql_connection_name': if Cloud SQL,
    #        'cloudsql_instance_name': if Cloud SQL,
    #        ...
    #    }

    # 2. Create Kubernetes secret for Cloud SQL credentials (if using Cloud SQL)
    #    kubectl create secret generic cloudsql-db-credentials \
    #      -n {namespace} \
    #      --from-literal=username={username} \
    #      --from-literal=password={password}

    # 3. Deploy n8n with Helm
    #    helm_runner = HelmRunner(charts_dir / "n8n")
    #    helm_runner.deploy_n8n(
    #        config,
    #        encryption_key,
    #        namespace=config.n8n_namespace,
    #        tls_enabled=False,  # TLS configured in Phase 4
    #        db_config=db_config
    #    )

    # 4. If using Cloud SQL, add Cloud SQL Proxy sidecar
    #    (either via Helm values or patch deployment)
```

**GCP-Specific Considerations**:
- **Cloud SQL Proxy**: Add sidecar container to n8n pods
- **Workload Identity**: Bind Kubernetes SA to Google SA
- **Secret Manager**: Mount secrets as volumes (alternative to Cloud SQL Proxy)

#### 6. GCP Teardown Class

**File**: `setup.py`
**Location**: After `AKSTeardown` class

**Requirements**:
```python
class GKETeardown:
    """Handles teardown of GCP GKE deployment"""

    def __init__(self, script_dir: Path, config: GCPDeploymentConfig):
        self.script_dir = script_dir
        self.config = config

    def execute(self) -> bool:
        """Execute 4-phase teardown (matches AWS/Azure pattern)"""

        # Phase 1: Uninstall Helm releases
        #   - helm uninstall n8n -n {namespace}
        #   - helm uninstall ingress-nginx -n ingress-nginx
        #   - helm uninstall cert-manager -n cert-manager (if exists)

        # Phase 2: Clean Kubernetes resources
        #   - kubectl delete pvc --all -n {namespace}
        #   - kubectl delete secret --all -n {namespace}
        #   - kubectl delete namespace {namespace}
        #   - kubectl delete namespace ingress-nginx
        #   - kubectl delete namespace cert-manager

        # Phase 3: Destroy Terraform infrastructure
        #   - terraform destroy (auto-approve if user confirmed)
        #   Destroys:
        #   - GKE cluster
        #   - Node pools
        #   - VPC network
        #   - Cloud NAT
        #   - Service accounts
        #   - Cloud SQL (if exists)

        # Phase 4: Clean Secret Manager
        #   - gcloud secrets delete {secret_name} --project={project_id}
        #   - Remove encryption keys
        #   - Remove basic auth credentials
```

**Pattern to Follow**: `TeardownRunner` (AWS, line 2498) and `AKSTeardown` (Azure, line 2956)

#### 7. Main Function Updates

**File**: `setup.py`
**Location**: `main()` function (line 3468)

**Required Changes**:

1. **Update argument parser** (line 3472):
```python
parser.add_argument('--cloud-provider', type=str, choices=['aws', 'azure', 'gcp'],
                   help='Cloud provider to use (aws, azure, or gcp)')
```

2. **Update cloud provider selection prompt** (line 3528):
```python
print(f"  {Colors.BOLD}1.{Colors.ENDC} AWS (Amazon Web Services) - EKS")
print(f"  {Colors.BOLD}2.{Colors.ENDC} Azure (Microsoft Azure) - AKS")
print(f"  {Colors.BOLD}3.{Colors.ENDC} GCP (Google Cloud Platform) - GKE\n")

choice = prompt.prompt_choice("Which cloud provider would you like to use?",
                             ["AWS", "Azure", "GCP"], default=0)
cloud_provider = "aws" if choice == "AWS" else ("azure" if choice == "Azure" else "gcp")
```

3. **Add GCP deployment flow** (after line 3876):
```python
elif cloud_provider == "gcp":
    # ═══════════════════════════════════════════════════════════════
    # GCP GKE DEPLOYMENT FLOW
    # ═══════════════════════════════════════════════════════════════

    # Collect GCP configuration
    print(f"\n{Colors.HEADER}Let's configure your GKE deployment...{Colors.ENDC}")
    prompt = ConfigurationPrompt(cloud_provider="gcp")
    config = prompt.collect_gcp_configuration(skip_tls=True)

    # Save configuration to history
    ConfigHistoryManager.save_configuration(config, "gcp", script_dir)

    # Create Terraform tfvars
    updater = FileUpdater(script_dir)
    updater.create_terraform_tfvars_gcp(config)

    # Deploy GCP infrastructure via Terraform
    terraform_dir = script_dir / "terraform" / "gcp"
    if not deploy_gcp_terraform(config, terraform_dir):
        raise Exception("GCP infrastructure deployment failed")

    # Deploy n8n application via Helm
    charts_dir = script_dir / "charts"
    if not deploy_gcp_helm(config, charts_dir, config.n8n_encryption_key):
        raise Exception("GCP n8n deployment failed")

    # Show useful commands
    print(f"\n{Colors.BOLD}Useful Commands:{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}kubectl get pods -n {config.n8n_namespace}{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}kubectl get ingress -n {config.n8n_namespace}{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}kubectl logs -f deployment/n8n -n {config.n8n_namespace}{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}kubectl get svc -n ingress-nginx{Colors.ENDC}")
```

4. **Add GCP teardown routing** (around line 3583):
```python
elif cloud_provider == "gcp":
    # GCP teardown flow
    config = GCPDeploymentConfig()

    # Try to detect config from GCP terraform.tfvars
    tfvars_path = script_dir / "terraform" / "gcp" / "terraform.tfvars"
    if tfvars_path.exists():
        # Parse tfvars to load configuration
        ...

    teardown = GKETeardown(script_dir, config)
    success = teardown.execute()
    sys.exit(0 if success else 1)
```

#### 8. Dependency Checker Updates

**File**: `setup.py`
**Location**: `DependencyChecker` class (around line 336)

**Required Changes**:

1. **Add GCP tools** (after line 346):
```python
GCP_TOOLS = {
    'gcloud': {
        'check_cmd': ['gcloud', 'version'],
        'description': 'Google Cloud SDK'
    },
}
```

2. **Update check_all_dependencies()** (line 389):
```python
def check_all_dependencies(cls, cloud_provider: str = "aws") -> Tuple[bool, list]:
    if cloud_provider == "gcp":
        required_tools = {**cls.COMMON_TOOLS, **cls.GCP_TOOLS}
    elif cloud_provider == "azure":
        required_tools = {**cls.COMMON_TOOLS, **cls.AZURE_TOOLS}
    else:
        required_tools = {**cls.COMMON_TOOLS, **cls.AWS_TOOLS}
```

### Required Terraform Modules

**Location**: `terraform/gcp/` directory (new)

**Required Files**:
1. `main.tf` - Main infrastructure definition
2. `variables.tf` - Input variables
3. `outputs.tf` - Terraform outputs
4. `versions.tf` - Provider versions
5. `vpc.tf` - VPC network configuration
6. `gke.tf` - GKE cluster and node pools
7. `secrets.tf` - Secret Manager integration
8. `cloudsql.tf` - Cloud SQL PostgreSQL (optional)

**Key Resources to Create** (based on AWS pattern):
```hcl
# VPC Network (equivalent to AWS VPC)
resource "google_compute_network" "vpc"
resource "google_compute_subnetwork" "private"
resource "google_compute_subnetwork" "public"

# Cloud NAT (equivalent to AWS NAT Gateway)
resource "google_compute_router" "router"
resource "google_compute_router_nat" "nat"

# GKE Cluster (equivalent to AWS EKS)
resource "google_container_cluster" "primary"
resource "google_container_node_pool" "primary_nodes"

# Service Accounts (equivalent to AWS IAM roles)
resource "google_service_account" "gke_cluster"
resource "google_service_account" "gke_nodes"
resource "google_service_account" "n8n_workload"

# Secret Manager (equivalent to AWS Secrets Manager)
resource "google_secret_manager_secret" "n8n_encryption_key"
resource "google_secret_manager_secret_version" "n8n_encryption_key_value"

# Cloud SQL (equivalent to AWS RDS) - Optional
resource "google_sql_database_instance" "postgres"
resource "google_sql_database" "n8n"
resource "google_sql_user" "n8n"

# Firewall Rules (equivalent to AWS Security Groups)
resource "google_compute_firewall" "allow_ingress"
```

### Estimated Implementation Effort

| Component | Complexity | Estimated Time |
|-----------|-----------|----------------|
| GCPDeploymentConfig class | Low | 2-3 hours |
| GCPAuthChecker class | Medium | 4-6 hours |
| GCP configuration prompts | Medium | 4-6 hours |
| Terraform GCP modules | High | 16-24 hours |
| GCP Helm deployment | Medium | 6-8 hours |
| GKETeardown class | Medium | 4-6 hours |
| Main function integration | Low | 2-3 hours |
| Testing & debugging | High | 8-12 hours |
| **Total** | | **46-68 hours** |

### Testing Requirements

1. **Unit Testing**:
   - GCP authentication checks
   - Configuration validation
   - Terraform tfvars generation

2. **Integration Testing**:
   - Full deployment workflow (SQLite)
   - Full deployment workflow (Cloud SQL)
   - Teardown workflow
   - Multi-region deployment
   - TLS configuration (Let's Encrypt)
   - Basic authentication

3. **Edge Cases**:
   - API not enabled errors
   - Insufficient permissions
   - LoadBalancer stuck in pending
   - Cloud SQL connectivity issues
   - Workload Identity binding failures

### Documentation Requirements

1. **Update docs/deployment/gcp.md** - Full deployment guide
2. **Update docs/getting-started.md** - Add GCP option
3. **Update README.md** - Add GCP to supported providers
4. **Update docs/reference/requirements.md** - Add GCP tools

## Next Steps

### Option 1: Manual Deployment (Current State)

Use this requirements guide to manually deploy n8n on GKE using:
1. gcloud CLI for authentication
2. Terraform for infrastructure (create modules based on AWS/Azure)
3. Helm for n8n deployment
4. kubectl for configuration

### Option 2: Automated Deployment (Future)

Once setup.py is updated with GCP support:
```bash
python3 setup.py --cloud-provider gcp
```

This will provide the same automated experience as AWS and Azure deployments.

---

*Last Updated: October 2025*
