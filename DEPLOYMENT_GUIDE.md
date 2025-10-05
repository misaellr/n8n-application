# N8N EKS Deployment Guide

## Overview
- Terraform provisions a dedicated VPC (three public and three private subnets), Internet/NAT gateways, an Amazon EKS 1.29 control plane, and a managed node group sized by `node_*` variables.
- AWS IAM roles are created for the control plane, worker nodes, and the AWS EBS CSI driver; the driver is enabled with a default `ebs-gp3` StorageClass.
- Sensitive settings (the n8n encryption key) are stored in AWS Systems Manager Parameter Store and injected into the Helm release at deploy time.
- Helm installs the upstream `ingress-nginx` chart (Network Load Balancer by default) and the bundled `helm/` chart deploys n8n with persistence, ingress, and optional TLS flows (no TLS, bring-your-own cert, or Let's Encrypt via cert-manager).
- The interactive CLI (`python3 setup.py`) orchestrates dependency checks, collects inputs, creates `terraform/terraform.tfvars`, and runs `terraform init`, `terraform plan`, and `terraform apply` end-to-end.

## Prerequisites
- macOS or Linux workstation with `python3`, Terraform >= 1.6, AWS CLI >= 2.0, kubectl, and Helm >= 3. The CLI verifies these before continuing.
- AWS credentials with permissions to create VPC, EC2, EKS, IAM, SSM, and load-balancer resources. Configure them with `aws configure --profile <profile>`.
- Optional: a DNS hostname if you plan to front n8n with TLS. Without a hostname the deployment still completes and you can use the load balancer DNS name.

## Deploy with the Setup CLI
1. From the repository root, run `python3 setup.py`.
2. Follow the prompts for AWS profile/region, cluster sizing, hostname, timezone, and TLS preference:
   - Leaving the encryption key blank lets Terraform generate a 64-character key and persist it to SSM.
   - Choosing `letsencrypt` requires an email address; the CLI toggles `enable_cert_manager = true` automatically.
   - Choosing `byo` asks for certificate and private key PEM files that are embedded into `terraform.tfvars`.
3. The CLI writes `terraform/terraform.tfvars`, then runs `terraform init`, `terraform plan`, and `terraform apply`. Expect ~25-30 minutes for the full stack to provision.
4. When Terraform finishes, the CLI executes the `configure_kubectl` output. If that step fails (for example when `aws` is not on `PATH`), rerun the printed command manually.
5. Review the rendered access instructions: they are derived from Terraform outputs and indicate whether TLS is active, which DNS records to create, and how to reach the UI.

### Artifacts Created by the CLI
- `terraform/terraform.tfvars` containing all answered prompts (including multi-line cert data when applicable).
- A generated encryption key if you declined to supply one; the key is saved in Parameter Store at `/n8n/encryption_key`.
- No changes are made to Terraform module defaults or `helm/values.yaml`; the Helm release consumes overrides via Terraform locals so you can re-run the CLI safely.

## Manual Command Reference
If you prefer to drive Terraform yourself (or need to re-run individual stages), use:
```bash
terraform fmt terraform/
(cd terraform && terraform init)
(cd terraform && terraform validate)
(cd terraform && terraform plan -out plan.out)
(cd terraform && terraform apply plan.out)
helm lint helm
helm template helm --values helm/values.yaml
```
When skipping the CLI you must create `terraform/terraform.tfvars` manually with the required values (`aws_profile`, `region`, `n8n_host`, and optionally `n8n_encryption_key` or TLS settings).

## Configuration Reference
- **Identity & Networking**
  - `aws_profile`, `region`, and `project_tag` set naming and tagging for all resources.
  - `vpc_cidr` defaults to `10.0.0.0/16`; subnets and NAT gateways are created per availability zone returned by `data.aws_availability_zones.available` (first three AZs).
- **Cluster & Nodes**
  - `cluster_name` defaults to `n8n-eks-cluster`, Kubernetes version `1.29`.
  - Worker capacity is controlled via `node_instance_types`, `node_desired_size`, `node_min_size`, and `node_max_size`.
- **Ingress & TLS**
  - `enable_nginx_ingress` installs `ingress-nginx` backed by an AWS Network Load Balancer.
  - `tls_certificate_source` accepts `none`, `byo`, or `letsencrypt` and drives additional resources: BYO creates a Kubernetes `Secret`; Let's Encrypt installs cert-manager and a `ClusterIssuer`.
  - `n8n_ingress_annotations` can be extended (for example, ALB annotations) through `terraform.tfvars`.
- **Application Settings**
  - `n8n_host` falls back to `<project_tag>.local` when left blank.
  - `n8n_encryption_key` defaults to empty; Terraform automatically generates a secure key when none is supplied.
  - `n8n_persistence_*` variables define the persistent volume claim (default 10 GiB using the gp3 StorageClass installed by Terraform).
  - Additional non-sensitive environment overrides can be added via `n8n_env_overrides`.

## TLS and DNS Scenarios
- **No TLS (`tls_certificate_source = "none"`)**: The ingress serves HTTP. Create a CNAME/ALIAS to the Network Load Balancer DNS if you still want friendly URLs.
- **Bring Your Own Certificate (`byo`)**: Supply PEM-encoded certificate and key. Terraform creates a namespaced TLS secret (`n8n_tls_secret_name`, default `n8n-tls`). Point DNS at the load balancer; traffic terminates with your certificate.
- **Let's Encrypt (`letsencrypt`)**: Ensure the hostname already resolves to the load balancer before Terraform applies. Cert-manager is installed, a `ClusterIssuer` is created, and certificates renew automatically.

## Post-Deployment Verification
```bash
# Configure kubectl (if the CLI was unable to run it automatically)
$(terraform output -raw configure_kubectl)

# Confirm cluster health
kubectl get nodes
kubectl get all -n n8n
kubectl get all -n ingress-nginx

# Fetch the load balancer hostname
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```
- Access the UI at the URL reported by `terraform output -raw n8n_url`. For HTTP deployments append the load balancer hostname manually.
- For Let's Encrypt deployments, confirm certificate readiness with `kubectl get certificate -n <namespace>`.

## Operational Tips
- Logs: `kubectl logs -f deployment/n8n -n n8n` and `kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller`.
- Storage: `kubectl get pvc -n n8n` ensures the PersistentVolume is bound to the gp3 StorageClass.
- Rolling Updates: modify `replicaCount` or enable the provided HPA in `helm/values.yaml`, then run `terraform apply` to push the change via Helm.

## Cost and Scaling Considerations
- Baseline monthly estimate in `us-east-1`: EKS control plane (~$73), one `t3.medium` worker (~$30), three NAT gateways (~$98), Network Load Balancer (~$16), gp3 volume (~$1). Adjust AZ count, instance type, or NAT strategy to reduce spend.
- To scale out: increase `node_max_size`, enable the Helm HPA, or integrate the Kubernetes Cluster Autoscaler (not included by default).

## Cleanup
To remove all resources (including the SSM parameter and Kubernetes workloads), run `terraform destroy` from the `terraform/` directory. Delete any DNS records you created afterwards.

## Further Reading
- N8N Documentation: https://docs.n8n.io/
- AWS EKS Best Practices: https://aws.github.io/aws-eks-best-practices/
- Terraform AWS Provider Docs: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Helm Documentation: https://helm.sh/docs/
