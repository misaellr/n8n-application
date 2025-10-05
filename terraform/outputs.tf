output "cluster_name" {
  value       = aws_eks_cluster.main.name
  description = "EKS cluster name"
}

output "cluster_endpoint" {
  value       = aws_eks_cluster.main.endpoint
  description = "EKS cluster endpoint"
}

output "cluster_security_group_id" {
  value       = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  description = "Security group ID attached to the EKS cluster"
}

output "cluster_arn" {
  value       = aws_eks_cluster.main.arn
  description = "EKS cluster ARN"
}

output "cluster_certificate_authority_data" {
  value       = aws_eks_cluster.main.certificate_authority[0].data
  description = "Base64 encoded certificate data for cluster authentication"
  sensitive   = true
}

output "region" {
  value       = var.region
  description = "AWS region where the cluster is deployed"
}

output "vpc_id" {
  value       = aws_vpc.main.id
  description = "VPC ID where EKS cluster is deployed"
}

output "private_subnet_ids" {
  value       = aws_subnet.private[*].id
  description = "Private subnet IDs for EKS nodes"
}

output "public_subnet_ids" {
  value       = aws_subnet.public[*].id
  description = "Public subnet IDs"
}

output "n8n_encryption_key_ssm_parameter" {
  value       = aws_ssm_parameter.n8n_encryption_key.name
  description = "SSM Parameter Store name for n8n encryption key"
}

output "nginx_ingress_controller_endpoint" {
  value       = var.enable_nginx_ingress ? "Run: kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'" : "NGINX Ingress Controller not enabled"
  description = "Command to get NGINX Ingress LoadBalancer endpoint"
}

output "configure_kubectl" {
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${aws_eks_cluster.main.name} --profile ${var.aws_profile}"
  description = "Command to configure kubectl for this EKS cluster"
}

output "n8n_namespace" {
  value       = var.n8n_namespace
  description = "Namespace where the n8n release is installed"
}

output "n8n_host" {
  value       = local.n8n_host
  description = "Hostname configured for n8n ingress and application URLs"
}

output "n8n_protocol" {
  value       = local.n8n_protocol
  description = "Protocol configured for n8n (http or https)"
}

output "n8n_url" {
  value       = "${local.n8n_protocol}://${local.n8n_host}"
  description = "Full URL to access n8n"
}

output "tls_certificate_source" {
  value       = var.tls_certificate_source
  description = "TLS certificate source: none, byo (bring your own), or letsencrypt"
}

output "tls_enabled" {
  value       = var.tls_certificate_source != "none"
  description = "Whether TLS/HTTPS is enabled"
}

output "cert_manager_installed" {
  value       = var.enable_cert_manager
  description = "Whether cert-manager is installed for Let's Encrypt certificate management"
}

output "letsencrypt_cluster_issuer" {
  value       = var.tls_certificate_source == "letsencrypt" ? "letsencrypt-${var.letsencrypt_environment}" : "Not configured"
  description = "ClusterIssuer name for Let's Encrypt (if configured)"
}

output "access_instructions" {
  value = var.tls_certificate_source == "none" ? join("\n", [
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "  N8N ACCESS INSTRUCTIONS (HTTP - No TLS)",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "",
    "1. Get the Load Balancer DNS:",
    "   kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'",
    "",
    "2. Access n8n via Load Balancer:",
    "   http://<load-balancer-dns>",
    "",
    "⚠️  WARNING: TLS is not configured. Communication is not encrypted.",
    "   Consider configuring TLS for production use.",
    "",
    "To configure TLS later, update terraform.tfvars with:",
    "  tls_certificate_source = \"letsencrypt\" or \"byo\"",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]) : var.tls_certificate_source == "byo" ? join("\n", [
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "  N8N ACCESS INSTRUCTIONS (HTTPS - BYO Certificate)",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "",
    "1. Ensure DNS record points to Load Balancer:",
    "   kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'",
    "",
    "2. Create DNS record:",
    "   ${local.n8n_host} → <load-balancer-dns> (CNAME or ALIAS)",
    "",
    "3. Access n8n via HTTPS:",
    "   ${local.n8n_protocol}://${local.n8n_host}",
    "",
    "✅ TLS Certificate: User-provided (Bring Your Own)",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]) : join("\n", [
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "  N8N ACCESS INSTRUCTIONS (HTTPS - Let's Encrypt)",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "",
    "1. Get the Load Balancer DNS:",
    "   kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'",
    "",
    "2. Create DNS record (REQUIRED for Let's Encrypt validation):",
    "   ${local.n8n_host} → <load-balancer-dns> (CNAME or ALIAS)",
    "",
    "3. Wait for Let's Encrypt certificate issuance (~2-5 minutes):",
    "   kubectl get certificate -n ${var.n8n_namespace}",
    "   kubectl describe certificate ${var.n8n_tls_secret_name} -n ${var.n8n_namespace}",
    "",
    "4. Access n8n via HTTPS:",
    "   ${local.n8n_protocol}://${local.n8n_host}",
    "",
    "✅ TLS Certificate: Auto-generated via Let's Encrypt (${var.letsencrypt_environment})",
    "♻️  Auto-renewal: Enabled (renews before expiration)",
    "",
    "Troubleshooting:",
    "  kubectl get certificaterequest -n ${var.n8n_namespace}",
    "  kubectl describe clusterissuer letsencrypt-${var.letsencrypt_environment}",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  ])
  description = "Instructions on how to access n8n based on TLS configuration"
}
