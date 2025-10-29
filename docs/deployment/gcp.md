# Deploy n8n on Google Kubernetes Engine (GKE)

Complete guide for deploying n8n workflow automation on Google Cloud Platform using our automated setup tool.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Steps](#detailed-steps)
- [Configuration Options](#configuration-options)
- [Post-Deployment](#post-deployment)
- [TLS/HTTPS Setup](#tlshttps-setup)
- [Basic Authentication](#basic-authentication)
- [Troubleshooting](#troubleshooting)
- [Cost Optimization](#cost-optimization)
- [Teardown](#teardown)

---

## Overview

This automated deployment creates:

- **GKE Cluster** (1 node, e2-medium) with autoscaling
- **VPC Network** with Cloud NAT for outbound internet
- **Cloud SQL PostgreSQL** (optional) or SQLite (default)
- **NGINX Ingress Controller** with LoadBalancer
- **Secret Manager** for encryption keys
- **Workload Identity** for secure pod-to-GCP authentication
- **TLS/HTTPS** via Let's Encrypt or BYO certificate
- **Basic Authentication** (optional)

**Deployment Time:** ~20-25 minutes
**Monthly Cost:** $80-$90 (SQLite) | $210-$220 (Cloud SQL PostgreSQL)

---

## Prerequisites

### 1. GCP Account Setup

- **GCP Project** with billing enabled
- **Project ID** - You'll need this during setup
- **gcloud CLI** installed and authenticated

```bash
# Verify gcloud is installed
gcloud version

# Login to GCP
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Verify authentication
gcloud config get-value project
```

### 2. Enable Required APIs

The setup script will prompt you to enable these if not already enabled:

```bash
gcloud services enable compute.googleapis.com
gcloud services enable container.googleapis.com
gcloud services enable servicenetworking.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable sqladmin.googleapis.com  # Only if using Cloud SQL
```

### 3. IAM Permissions

Your GCP user needs the following roles:

**Required:**
- `roles/compute.networkAdmin` - VPC, subnets, Cloud NAT
- `roles/container.clusterAdmin` - GKE cluster management
- `roles/iam.serviceAccountAdmin` - Service account creation
- `roles/iam.serviceAccountUser` - Attach service accounts
- `roles/secretmanager.admin` - Secret Manager operations

**Optional (PostgreSQL only):**
- `roles/cloudsql.admin` - Cloud SQL management

**Quick assign:**
```bash
USER_EMAIL=$(gcloud config get-value account)
PROJECT_ID=$(gcloud config get-value project)

for role in compute.networkAdmin container.clusterAdmin iam.serviceAccountAdmin iam.serviceAccountUser secretmanager.admin; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="user:$USER_EMAIL" \
    --role="roles/$role"
done
```

See [IAM Permissions Matrix](../reference/iam-permissions-matrix.md#gcp-iam-permissions) for details.

### 4. Required Tools

Install these tools on your local machine:

**macOS (Homebrew):**
```bash
brew install --cask google-cloud-sdk
gcloud components install gke-gcloud-auth-plugin
brew tap hashicorp/tap
brew install hashicorp/tap/terraform kubectl helm python@3.11
```

**Linux (Ubuntu/Debian):**
```bash
# Google Cloud SDK
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
sudo apt-get update && sudo apt-get install google-cloud-sdk google-cloud-cli-gke-gcloud-auth-plugin

# Terraform
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform

# kubectl and Helm
sudo snap install kubectl --classic
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Python 3.8+
sudo apt install python3 python3-pip
```

**Verify installations:**
```bash
gcloud version
terraform version
kubectl version --client
helm version
python3 --version
```

---

## Quick Start

### Step 1: Clone Repository

```bash
git clone https://github.com/YOUR_ORG/n8n-application.git
cd n8n-application
```

### Step 2: Run Setup

```bash
python3 setup.py --cloud-provider gcp
```

### Step 3: Follow Interactive Prompts

The script will ask you for:

1. **GCP Project ID** - Your Google Cloud project
2. **Region** - e.g., `us-central1` (default)
3. **Cluster Name** - e.g., `n8n-gke-cluster` (default)
4. **Node Configuration** - Machine type and count
5. **Domain Name** - Your domain for n8n (e.g., `n8n.example.com`)
6. **Database Type** - SQLite (free) or Cloud SQL PostgreSQL
7. **TLS Configuration** - Skip for now or configure later

### Step 4: Wait for Deployment

```
📦 PHASE 1: Deploying Infrastructure (~8-10 minutes)
  ✓ VPC and subnets created
  ✓ Cloud NAT configured
  ✓ GKE cluster provisioned
  ✓ Node pool ready

🚀 PHASE 2: Deploying n8n Application (~5 minutes)
  ✓ NGINX ingress controller installed
  ✓ n8n deployed
  ✓ Secrets configured

✅ Deployment Complete!
```

### Step 5: Access n8n

```bash
# Get LoadBalancer IP
kubectl get svc -n ingress-nginx ingress-nginx-controller

# Access n8n
http://<LOADBALANCER_IP>:5678
```

**Next:** [Configure DNS](#configure-dns) and [enable TLS](#tlshttps-setup)

---

## Detailed Steps

### Configuration Prompts Explained

#### 1. GCP Project ID

```
Enter your GCP project ID: cross-cloud-475812
```

**How to find:**
```bash
gcloud projects list
```

**Important:**
- Must be exact project ID, not project name
- Project must have billing enabled
- You must have necessary IAM permissions

#### 2. GCP Region

```
GCP Region [us-central1]:
```

**Options:**
- `us-central1` (Iowa) - Lowest cost, recommended
- `us-east1` (South Carolina)
- `us-west1` (Oregon)
- `europe-west1` (Belgium)
- `asia-east1` (Taiwan)

**Considerations:**
- Choose region closest to your users
- All resources will be in this region
- Cost varies slightly by region

#### 3. Cluster Name

```
GKE cluster name [n8n-gke-cluster]:
```

**Default:** `n8n-gke-cluster`

**Naming rules:**
- 1-40 characters
- Lowercase letters, numbers, hyphens only
- Must start with a letter

#### 4. Node Configuration

```
Node machine type [e2-medium]:
Node count [1]:
```

**Machine Types:**
| Type | vCPUs | RAM | Cost/month | Use Case |
|------|-------|-----|------------|----------|
| **e2-micro** | 0.25-2 | 1 GB | $6-7 | Testing only |
| **e2-small** | 0.5-2 | 2 GB | $13-14 | Light workloads |
| **e2-medium** | 1-2 | 4 GB | $27-28 | **Recommended** |
| **n2-standard-2** | 2 | 8 GB | $70 | Heavy workflows |

**Node Count:**
- **1 node:** Development/testing, lower cost
- **2-3 nodes:** Production, high availability
- Autoscaling enabled by default (1-5 nodes)

#### 5. Domain Name

```
Domain name for n8n (e.g., n8n.example.com): n8n-gcp.mycompany.com
```

**Important:**
- You must own this domain
- Will be used for ingress configuration
- Must point to LoadBalancer IP after deployment

**Options:**
- Custom domain (recommended): `n8n.example.com`
- Temporary testing: Use LoadBalancer IP directly
- Subdomain: `n8n-prod.example.com`

#### 6. Database Type

```
Database Type:
  1. SQLite (file-based, free)
  2. Cloud SQL PostgreSQL (~$120/month)

Choice [1]:
```

**SQLite (Default):**
- ✅ Free (no database costs)
- ✅ Simple setup
- ✅ Good for <1000 workflows
- ⚠️ Single-node only (no HA)
- ⚠️ Limited concurrent executions

**Cloud SQL PostgreSQL:**
- ✅ Scalable
- ✅ High availability
- ✅ Automatic backups
- ✅ Supports clustering
- ❌ Adds $120-180/month cost
- **Use for:** Production with many workflows

**Cloud SQL Configuration (if selected):**
```
PostgreSQL instance size [db-f1-micro]:
Storage size (GB) [20]:
Enable high availability (2x cost) [N]:
```

#### 7. TLS/HTTPS (Skippable)

```
Configure TLS/HTTPS now? [N]:
```

**Recommendation:** Skip during initial deployment

**Why:**
- Requires DNS to be configured first
- Can be added later with `python3 setup.py --configure-tls`
- See [TLS/HTTPS Setup](#tlshttps-setup) section

---

## Configuration Options

### Customizing terraform.tfvars

After initial deployment, you can modify `terraform/gcp/terraform.tfvars`:

```hcl
# Auto-generated by setup.py - N8N GCP GKE Infrastructure
gcp_project_id = "cross-cloud-475812"
gcp_region     = "us-central1"
gcp_zone       = "us-central1-a"

# VPC
vpc_name    = "n8n-vpc"
subnet_name = "n8n-subnet"
subnet_cidr = "10.0.0.0/24"

# GKE Cluster
cluster_name       = "n8n-gke-cluster"
node_count         = 1
node_machine_type  = "e2-medium"
min_node_count     = 1
max_node_count     = 5
enable_autoscaling = true

# Application
n8n_host      = "n8n-gcp.example.com"
n8n_namespace = "n8n"
timezone      = "America/New_York"

# Database
database_type = "sqlite"  # or "cloudsql"
postgres_instance_tier = "db-f1-micro"
postgres_storage_gb    = 20
```

### Re-deploying with Changes

```bash
cd terraform/gcp
terraform plan   # Review changes
terraform apply  # Apply changes
```

---

## Post-Deployment

### 1. Verify Deployment

```bash
# Check cluster
gcloud container clusters list --region us-central1

# Check kubectl connection
kubectl config current-context
# Should show: gke_PROJECT_us-central1_n8n-gke-cluster

# Check n8n pod
kubectl get pods -n n8n
# NAME                   READY   STATUS    RESTARTS   AGE
# n8n-xxxxx-xxxxx        1/1     Running   0          5m

# Check ingress
kubectl get svc -n ingress-nginx
# NAME                       TYPE           EXTERNAL-IP      PORT(S)
# ingress-nginx-controller   LoadBalancer   34.xxx.xxx.xxx   80:32080/TCP,443:32443/TCP
```

### 2. Configure DNS

**Get LoadBalancer IP:**
```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

**Add DNS record:**

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | n8n-gcp | 34.xxx.xxx.xxx | 300 |

**Or using Cloud DNS:**
```bash
gcloud dns record-sets create n8n-gcp.example.com. \
  --type=A \
  --ttl=300 \
  --rrdatas="34.xxx.xxx.xxx" \
  --zone=my-zone
```

**Verify DNS:**
```bash
nslookup n8n-gcp.example.com
dig n8n-gcp.example.com +short
```

### 3. Access n8n

Once DNS propagates (5-10 minutes):

```
http://n8n-gcp.example.com
```

**Initial Setup:**
1. Create owner account (email + password)
2. Set up workflows
3. Configure credentials

**⚠️ Important:** Your n8n is currently **publicly accessible without authentication**. See [Basic Authentication](#basic-authentication) to secure it.

---

## TLS/HTTPS Setup

### Prerequisites

✅ n8n deployed successfully
✅ DNS configured and propagated
✅ Domain resolves to LoadBalancer IP

### Option 1: Let's Encrypt (Recommended)

```bash
python3 setup.py --cloud-provider gcp --configure-tls
```

**Interactive prompts:**

1. **TLS Certificate Source:**
   - Choose: `Let's Encrypt (auto-generated, HTTP-01 validation)`

2. **Email Address:**
   ```
   Let's Encrypt email: your-email@example.com
   ```
   - Used for certificate expiration notices
   - Required by Let's Encrypt

3. **Environment:**
   ```
   Use Let's Encrypt staging (for testing) or production? [staging]:
   ```
   - **staging**: For testing (avoids rate limits)
   - **production**: For real certificates

**What happens:**
1. ✅ cert-manager installed
2. ✅ ClusterIssuer created
3. ✅ Certificate requested from Let's Encrypt
4. ✅ n8n ingress updated to use HTTPS
5. ✅ HTTP → HTTPS redirect enabled

**Verify:**
```bash
# Check certificate
kubectl get certificate -n n8n

# Check if ready
kubectl describe certificate n8n-tls -n n8n
```

**Access:**
```
https://n8n-gcp.example.com  ← Now with HTTPS! 🔒
```

### Option 2: Bring Your Own Certificate

If you have your own TLS certificate:

```bash
python3 setup.py --cloud-provider gcp --configure-tls
```

1. **TLS Certificate Source:**
   - Choose: `Bring Your Own Certificate (provide PEM files)`

2. **Provide Certificate Files:**
   ```
   Path to TLS certificate file (PEM format): /path/to/cert.pem
   Path to TLS private key file (PEM format): /path/to/key.pem
   ```

3. Certificate validation and deployment

**Certificate Requirements:**
- PEM format
- Valid for your domain
- Not expired
- Includes intermediate certificates (if applicable)

### Troubleshooting TLS

**Certificate not issued:**
```bash
# Check certificate request status
kubectl describe certificaterequest -n n8n

# Check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager
```

**Common issues:**

| Issue | Cause | Fix |
|-------|-------|-----|
| DNS not propagating | Domain doesn't resolve | Wait 10-30 minutes, verify with `dig` |
| HTTP-01 challenge fails | LoadBalancer not accessible | Check firewall rules, security groups |
| Rate limit hit | Too many cert requests | Use staging environment first |

---

## Basic Authentication

Protect your n8n with username/password authentication.

### Enable Basic Auth

```bash
python3 setup.py --cloud-provider gcp --configure-basic-auth
```

**Prompts:**
```
Enable basic authentication? [Y/n]: Y
```

**Auto-generated credentials:**
```
✓ Generated basic auth credentials

⚠️  IMPORTANT - Save these credentials!
============================================================
Username: admin
Password: Kx9mP2nQ8vR3
============================================================

Save these credentials securely!
```

**What happens:**
1. ✅ htpasswd secret created
2. ✅ Ingress updated with auth annotations
3. ✅ Browser will prompt for username/password

**Access:**
- Browser prompts for credentials
- Enter username: `admin`
- Enter generated password
- Or use: `https://admin:Kx9mP2nQ8vR3@n8n-gcp.example.com`

### Disable Basic Auth

```bash
helm upgrade n8n ./charts/n8n -n n8n \
  --reuse-values \
  --set ingress.annotations."nginx\.ingress\.kubernetes\.io/auth-type"=null \
  --set ingress.annotations."nginx\.ingress\.kubernetes\.io/auth-secret"=null \
  --set ingress.annotations."nginx\.ingress\.kubernetes\.io/auth-realm"=null
```

---

## Troubleshooting

### Common Issues

#### 1. API Not Enabled

**Error:**
```
Error: Error creating Network: googleapi: Error 403: Compute Engine API has not been used
```

**Fix:**
```bash
gcloud services enable compute.googleapis.com container.googleapis.com secretmanager.googleapis.com
```

#### 2. Insufficient Permissions

**Error:**
```
Error: Error creating Cluster: Permission denied
```

**Fix:** Assign required IAM roles (see [Prerequisites](#iam-permissions))

#### 3. Project Quota Exceeded

**Error:**
```
Error: Quota 'CPUS' exceeded. Limit: 8.0 in region us-central1.
```

**Fix:**
```bash
# Check quotas
gcloud compute project-info describe --project=PROJECT_ID

# Request quota increase (Google Cloud Console)
# IAM & Admin > Quotas
```

#### 4. LoadBalancer Stuck in Pending

**Symptoms:**
```bash
kubectl get svc -n ingress-nginx
# EXTERNAL-IP shows <pending>
```

**Diagnosis:**
```bash
kubectl describe svc ingress-nginx-controller -n ingress-nginx
```

**Common causes:**
- Insufficient quota for external IPs
- Firewall rules blocking LoadBalancer
- Region doesn't support LoadBalancers (unlikely for standard regions)

**Fix:**
```bash
# Check firewall rules
gcloud compute firewall-rules list

# Ensure health check can reach nodes
gcloud compute firewall-rules create allow-health-check \
  --allow tcp:80,tcp:443 \
  --source-ranges 130.211.0.0/22,35.191.0.0/16
```

#### 5. Certificate Challenge Fails

**Symptoms:**
```bash
kubectl describe certificate n8n-tls -n n8n
# Events show "Failed to verify HTTP-01 challenge"
```

**Diagnosis:**
```bash
# Test if domain is accessible
curl http://n8n-gcp.example.com/.well-known/acme-challenge/test
```

**Fix:**
1. Verify DNS resolves to LoadBalancer IP
2. Check ingress is working: `kubectl get ingress -n n8n`
3. Use staging environment to test
4. Wait 60 seconds and retry

#### 6. Cloud SQL Connection Fails

**Symptoms:**
```bash
kubectl logs deployment/n8n -n n8n
# Error: Connection to Cloud SQL failed
```

**Diagnosis:**
```bash
# Check Cloud SQL instance
gcloud sql instances describe n8n-postgres --project=PROJECT_ID

# Check workload identity binding
gcloud iam service-accounts get-iam-policy \
  n8n-cloudsql@PROJECT_ID.iam.gserviceaccount.com
```

**Fix:**
```bash
# Ensure Cloud SQL Admin API is enabled
gcloud services enable sqladmin.googleapis.com

# Verify service account has cloudsql.client role
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:n8n-cloudsql@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

### Debug Commands

```bash
# Check all n8n resources
kubectl get all -n n8n

# Check pod logs
kubectl logs -f deployment/n8n -n n8n

# Describe pod for events
kubectl describe pod -n n8n -l app.kubernetes.io/name=n8n

# Check secrets
kubectl get secrets -n n8n

# Check ingress configuration
kubectl describe ingress -n n8n

# GKE cluster info
gcloud container clusters describe n8n-gke-cluster --region us-central1

# Terraform state
cd terraform/gcp
terraform show
```

### Get Help

**Logs to collect:**
1. `setup_history.log` - Deployment configuration
2. `kubectl logs deployment/n8n -n n8n` - n8n application logs
3. `kubectl describe pod -n n8n` - Pod events
4. `terraform show` output

**Resources:**
- [GCP Requirements Guide](../guides/gcp-requirements.md)
- [IAM Permissions Matrix](../reference/iam-permissions-matrix.md)
- [n8n Community](https://community.n8n.io/)

---

## Cost Optimization

### Monthly Cost Breakdown

#### SQLite Configuration (Default)

| Resource | Specification | Cost/Month |
|----------|---------------|------------|
| **GKE Control Plane** | Free (1 cluster per billing account) | $0 |
| **GKE Nodes** | e2-medium × 1 node | $27-28 |
| **Persistent Disk** | 10 GB standard | $0.40 |
| **Cloud NAT** | Includes 32 GB data | $45 |
| **LoadBalancer** | 1 forwarding rule | $18 |
| **Secret Manager** | < 10 secrets | $0.06 |
| **Egress (estimate)** | ~50 GB/month | $6 |
| **Total** | | **~$96-97/month** |

#### Cloud SQL Configuration

Add to above:

| Resource | Specification | Cost/Month |
|----------|---------------|------------|
| **Cloud SQL Instance** | db-f1-micro, 20 GB | $14 |
| **Cloud SQL Storage** | 20 GB SSD | $3.40 |
| **Cloud SQL Backups** | 7 days retained | $1.20 |
| **Cloud SQL Proxy** | Included | $0 |
| **Additional** | | **+$18-20/month** |

**Total with PostgreSQL:** ~$114-117/month

### Cost Reduction Tips

#### 1. Use Preemptible Nodes (Save ~70%)

**⚠️ NOT recommended for production** - nodes can be terminated at any time

```hcl
# terraform/gcp/terraform.tfvars
preemptible_nodes = true  # Reduces node cost from $27 to $8/month
```

#### 2. Reduce Cloud NAT Costs

**Problem:** Cloud NAT charges for:
- NAT gateway per zone: $0.045/hour = ~$33/month
- Data processed: $0.045/GB

**Options:**
- Accept the cost (simplest, most reliable)
- Use Cloud VPN or Interconnect (complex, only for high traffic)

**Cloud NAT is required for:**
- Pulling Docker images
- n8n webhooks to external services
- Let's Encrypt HTTP-01 challenges

#### 3. Right-Size Node Machine Type

**Current:** e2-medium (1-2 vCPU, 4 GB RAM) - $27/month

**Alternatives:**
| Type | Cost | When to Use |
|------|------|-------------|
| e2-small | $13/month | Light workflows (<10 concurrent) |
| e2-micro | $6/month | Testing only (not production) |
| e2-medium | $27/month | **Recommended** (1-50 workflows) |
| n2-standard-2 | $70/month | Heavy workflows (>100 concurrent) |

#### 4. Use SQLite Instead of Cloud SQL

**Savings:** $18-20/month

**Trade-offs:**
- ❌ No high availability
- ❌ Limited concurrent executions
- ❌ Single-node only
- ✅ Free
- ✅ Simpler setup

**When to use SQLite:**
- Development/testing
- Small teams (<10 users)
- <1000 workflows
- <50 concurrent executions

#### 5. Delete Resources When Not in Use

```bash
# Stop GKE cluster (saves node costs but keeps data)
gcloud container clusters resize n8n-gke-cluster \
  --num-nodes=0 \
  --region us-central1

# Start again
gcloud container clusters resize n8n-gke-cluster \
  --num-nodes=1 \
  --region us-central1

# Or fully tear down (see Teardown section)
```

### Free Tier Credits

**GCP Free Tier:**
- First cluster free (control plane)
- $300 free credits for new accounts (90 days)
- Always free: 1 f1-micro instance (not e2-micro)

---

## Teardown

### Quick Teardown

```bash
python3 setup.py --cloud-provider gcp --teardown
```

**What gets deleted:**
- ✅ GKE cluster and nodes
- ✅ VPC and subnets
- ✅ Cloud NAT and external IPs
- ✅ Cloud SQL instance (if used)
- ✅ Secret Manager secrets
- ✅ Service accounts
- ✅ LoadBalancer

**What's preserved:**
- ✅ Persistent disks (backups recommended)
- ✅ Cloud Storage buckets (if created manually)
- ✅ DNS records (must delete manually)

### Manual Teardown

```bash
cd terraform/gcp
terraform destroy
```

**Confirm when prompted:**
```
Do you really want to destroy all resources?
  Terraform will destroy all your managed infrastructure, as there is no undo.
  Only 'yes' will be accepted to confirm.

  Enter a value: yes
```

### Known Issue: Terraform Provider Bug

**Symptom:**
```
Error: Error waiting for Deleting Network: The network resource 'projects/PROJECT/global/networks/n8n-vpc' is already being used by 'projects/PROJECT/global/firewalls/gke-n8n-gke-cluster-xxx'
```

**Cause:** Google Terraform provider doesn't wait for GKE-managed firewall rules to be deleted before deleting VPC.

**Workaround (Automated):**

Our Terraform configuration includes deletion_policy = "ABANDON" for the network, which works around this bug.

**Manual cleanup if needed:**
```bash
# List remaining firewall rules
gcloud compute firewall-rules list --filter="network:n8n-vpc"

# Delete GKE-managed firewall rules
gcloud compute firewall-rules delete gke-n8n-gke-cluster-xxx --quiet

# Delete VPC
gcloud compute networks delete n8n-vpc --quiet
```

See [GCP Teardown Known Issue](../guides/gcp-teardown-known-issue.md) for details.

### Verify Teardown

```bash
# Check GKE clusters
gcloud container clusters list --region us-central1

# Check VPCs
gcloud compute networks list

# Check Cloud SQL instances
gcloud sql instances list

# Check remaining costs
gcloud billing projects describe PROJECT_ID
```

---

## Production Checklist

Before going to production:

- [ ] TLS/HTTPS configured with production certificates
- [ ] Basic authentication enabled
- [ ] DNS configured correctly
- [ ] Cloud SQL PostgreSQL instead of SQLite
- [ ] At least 2 nodes for high availability
- [ ] Backups configured (Cloud SQL automatic backups enabled)
- [ ] Monitoring enabled (Cloud Operations)
- [ ] Cost alerts configured
- [ ] IAM roles reviewed (least privilege)
- [ ] Network security reviewed (firewall rules)
- [ ] Disaster recovery plan documented
- [ ] Workflow execution tested end-to-end

---

## Next Steps

- **Configure Workflows:** Build your first n8n workflow
- **Set Up Monitoring:** Enable Cloud Operations/Logging
- **Scale Cluster:** Increase node count for HA
- **Database Migration:** Switch from SQLite to Cloud SQL
- **CI/CD Integration:** Automate deployments

---

## Related Documentation

- [GCP Requirements Guide](../guides/gcp-requirements.md) - Prerequisites and setup
- [IAM Permissions Matrix](../reference/iam-permissions-matrix.md) - Detailed permissions
- [GCP Teardown Known Issue](../guides/gcp-teardown-known-issue.md) - Terraform bug workaround
- [GCP Lessons Learned](../guides/gcp-lessons-learned.md) - Common pitfalls

---

*Last Updated: October 28, 2025*
*Validated with: setup.py v2.0, Terraform v1.6, GKE 1.27+*
