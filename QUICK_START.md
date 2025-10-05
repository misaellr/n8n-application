# N8N on AWS EKS - Quick Start

## 1. Verify Tooling
```bash
terraform version    # >= 1.6
aws --version        # >= 2.0
kubectl version --client
helm version         # >= 3.0
```
Install any missing tools before continuing.

## 2. Configure AWS Credentials
```bash
aws configure --profile <profile-name>
aws sts get-caller-identity --profile <profile-name>
```
Use an IAM principal with permissions for VPC, EC2, EKS, IAM, SSM, and Elastic Load Balancing.

## 3. Run the Guided Setup
```bash
python3 setup.py
```
The CLI checks dependencies, prompts for deployment inputs, writes `terraform/terraform.tfvars`, and executes `terraform init`, `terraform plan`, and `terraform apply` for you. Leave the encryption key blank to auto-generate a secure value stored in AWS Systems Manager Parameter Store. Choose `none`, `byo`, or `letsencrypt` when asked about TLS.

## 4. Watch Terraform Complete
Provisioning takes roughly 25-30 minutes. The script prints Terraform progress and surfaces any errors. When the stack is ready it runs the `configure_kubectl` command from Terraform outputs; rerun that command manually if it fails.

## 5. Validate the Cluster and n8n
```bash
# Configure kubectl if needed
$(terraform output -raw configure_kubectl)

# Check infrastructure
kubectl get nodes
kubectl get pods -n n8n
kubectl get ingress -n n8n
kubectl get svc -n ingress-nginx
```
Terraform also prints `access_instructions`, `n8n_url`, and the Parameter Store path for the encryption key.

## 6. Configure DNS and TLS
```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```
- Point your hostname to the load balancer DNS name (CNAME/ALIAS).
- For Let's Encrypt deployments keep the record in place until the certificate shows `Ready` (`kubectl get certificate -n n8n`).

## 7. Cleanup
Destroy the environment when finished:
```bash
(cd terraform && terraform destroy)
```
Remove any DNS entries created for the deployment.

---
Need more detail? See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md).
