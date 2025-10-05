# N8N on AWS EKS - Quick Start

## 1. Verify Tooling
```bash
terraform version    # >= 1.6
aws --version        # >= 2.0
kubectl version --client
helm version         # >= 3.0
python3 --version    # >= 3.7
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

The CLI performs a **4-phase deployment**:

### Phase 1: Infrastructure (~22-27 minutes)
- VPC, subnets, NAT gateways
- EKS cluster and node group
- NGINX ingress controller (creates LoadBalancer)
- EBS CSI driver and StorageClass

### Phase 2: Application (~2-3 minutes)
- Deploys n8n via Helm CLI
- Initially deployed with HTTP only (no TLS)
- Creates namespace, PVC, deployment, service, ingress

### Phase 3: LoadBalancer Retrieval (~1-2 minutes)
- Retrieves LoadBalancer DNS automatically
- Displays access URL: `http://<load-balancer-dns>`

### Phase 4: TLS Configuration (Optional, ~5 minutes)
- **Interactive prompt** after LoadBalancer is ready
- You can skip TLS initially or configure it now
- Two options:
  - **Bring Your Own Certificate**: Provide PEM files
  - **Let's Encrypt**: Auto-generated via HTTP-01 validation

**Important**: For Let's Encrypt, you must configure DNS **before** the setup proceeds:
```
1. Create DNS record for: your-domain.com
2. Point to LoadBalancer: a1234567890.us-east-1.elb.amazonaws.com
3. Confirm DNS is configured
4. Setup proceeds with cert-manager installation
```

## 4. Watch the Deployment

The script shows clear progress for each phase. Total time: **~25-35 minutes**.

When complete, you'll see:
```
============================================================
  🎉 N8N DEPLOYMENT COMPLETE!
============================================================

Your n8n instance is now running!

LoadBalancer URL: a1234567890.us-east-1.elb.amazonaws.com
Access n8n at:    http://a1234567890.us-east-1.elb.amazonaws.com

⚠  Currently using HTTP (unencrypted)
```

## 5. Validate the Deployment
```bash
# Check cluster nodes
kubectl get nodes

# Check n8n pods
kubectl get pods -n n8n

# Check ingress
kubectl get ingress -n n8n

# View n8n logs
kubectl logs -f deployment/n8n -n n8n

# Check LoadBalancer service
kubectl get svc -n ingress-nginx
```

## 6. Configure TLS (If Skipped)

If you skipped TLS during initial setup, configure it later:

```bash
python3 setup.py --configure-tls
```
*(Feature coming soon)*

Or manually:
1. Configure DNS to point to your LoadBalancer
2. For Let's Encrypt:
   ```bash
   helm install cert-manager https://charts.jetstack.io/charts/cert-manager-v1.13.3.tgz \
     --namespace cert-manager --create-namespace --set installCRDs=true

   # Create ClusterIssuer (see DEPLOYMENT_GUIDE.md for YAML)
   kubectl apply -f cluster-issuer.yaml

   # Upgrade n8n with TLS enabled
   helm upgrade n8n ./helm -n n8n \
     --reuse-values \
     --set ingress.tls.enabled=true \
     --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt-production'
   ```

3. For BYO Certificate:
   ```bash
   kubectl create secret tls n8n-tls -n n8n \
     --cert=path/to/cert.pem \
     --key=path/to/key.pem

   helm upgrade n8n ./helm -n n8n \
     --reuse-values \
     --set ingress.tls.enabled=true
   ```

## 7. Monitor Let's Encrypt Certificate (If Used)

```bash
# Watch certificate issuance (~2-5 minutes)
kubectl get certificate -n n8n -w

# Check certificate status
kubectl describe certificate n8n-tls -n n8n

# View cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager
```

Once certificate shows `READY=True`, access n8n at `https://your-domain.com`

## 8. Cleanup

Destroy the environment when finished:
```bash
(cd terraform && terraform destroy)
```

**Note**: Terraform will **not** destroy Helm-deployed resources automatically. Clean up manually:
```bash
helm uninstall n8n -n n8n
helm uninstall cert-manager -n cert-manager  # if installed
kubectl delete namespace n8n cert-manager
```

Remove any DNS entries created for the deployment.

---

## Troubleshooting

**LoadBalancer not ready after 5 minutes:**
```bash
kubectl describe svc -n ingress-nginx ingress-nginx-controller
kubectl get events -n ingress-nginx
```

**n8n pod not starting:**
```bash
kubectl describe pod -n n8n -l app=n8n
kubectl logs -n n8n -l app=n8n
```

**Let's Encrypt certificate stuck in Pending:**
```bash
# Check DNS resolution
nslookup your-domain.com

# Check certificate request
kubectl get certificaterequest -n n8n
kubectl describe certificaterequest -n n8n <name>

# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager --tail=100
```

---

Need more detail? See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md).
