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

output "nlb_elastic_ips" {
  value       = var.enable_nginx_ingress ? "EIPs are auto-managed by AWS NLB service. Get IPs via: kubectl get svc -n ingress-nginx ingress-nginx-controller" : "NGINX Ingress Controller not enabled"
  description = "Network Load Balancer uses AWS-managed Elastic IPs (prevents orphaned resources)"
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

output "n8n_encryption_key_value" {
  value       = data.aws_ssm_parameter.n8n_encryption_key.value
  description = "N8N encryption key from SSM (for helm deployment)"
  sensitive   = true
}

########################################
# Database Outputs
########################################
output "database_type" {
  value       = var.database_type
  description = "Database backend type (sqlite or postgresql)"
}

output "rds_endpoint" {
  value       = var.database_type == "postgresql" ? aws_db_instance.n8n[0].endpoint : null
  description = "RDS PostgreSQL endpoint (null if using SQLite)"
}

output "rds_address" {
  value       = var.database_type == "postgresql" ? aws_db_instance.n8n[0].address : null
  description = "RDS PostgreSQL address (null if using SQLite)"
}

output "rds_port" {
  value       = var.database_type == "postgresql" ? aws_db_instance.n8n[0].port : null
  description = "RDS PostgreSQL port (null if using SQLite)"
}

output "rds_database_name" {
  value       = var.database_type == "postgresql" ? var.rds_database_name : null
  description = "RDS PostgreSQL database name (null if using SQLite)"
}

output "rds_username" {
  value       = var.database_type == "postgresql" ? var.rds_username : null
  description = "RDS PostgreSQL username (null if using SQLite)"
  sensitive   = true
}

output "rds_password" {
  value       = var.database_type == "postgresql" ? random_password.rds_password[0].result : null
  description = "RDS PostgreSQL password (null if using SQLite)"
  sensitive   = true
}

########################################
# Basic Auth Outputs
########################################
output "basic_auth_enabled" {
  value       = var.enable_basic_auth
  description = "Whether basic authentication is enabled"
}
