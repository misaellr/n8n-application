########################################
# Azure Resource Group Outputs
########################################
output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "Location of the resource group"
  value       = azurerm_resource_group.main.location
}

########################################
# AKS Cluster Outputs
########################################
output "cluster_name" {
  description = "Name of the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.name
}

output "cluster_endpoint" {
  description = "Endpoint for the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.kube_config[0].host
  sensitive   = true
}

output "cluster_id" {
  description = "ID of the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.id
}

output "kubeconfig" {
  description = "Kubeconfig for accessing the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.kube_config_raw
  sensitive   = true
}

output "get_kubeconfig_command" {
  description = "Command to retrieve kubeconfig"
  value       = "az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${azurerm_kubernetes_cluster.main.name} --overwrite-existing"
}

########################################
# Network Outputs
########################################
output "vnet_id" {
  description = "ID of the Virtual Network"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "Name of the Virtual Network"
  value       = azurerm_virtual_network.main.name
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = azurerm_subnet.private[*].id
}

output "nat_gateway_ip" {
  description = "Public IP address of the NAT Gateway"
  value       = azurerm_public_ip.nat.ip_address
}

########################################
# Load Balancer Outputs
########################################
output "load_balancer_ip" {
  description = "Public IP address for the Load Balancer"
  value       = var.enable_nginx_ingress ? azurerm_public_ip.lb[0].ip_address : null
}

output "n8n_url" {
  description = "URL to access n8n application"
  value       = var.enable_nginx_ingress ? "${var.n8n_protocol}://${var.n8n_host}" : "Load balancer not enabled"
}

########################################
# Key Vault Outputs
########################################
output "key_vault_id" {
  description = "ID of the Azure Key Vault"
  value       = azurerm_key_vault.main.id
}

output "key_vault_name" {
  description = "Name of the Azure Key Vault"
  value       = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  description = "URI of the Azure Key Vault"
  value       = azurerm_key_vault.main.vault_uri
}

########################################
# PostgreSQL Outputs (if enabled)
########################################
output "postgres_fqdn" {
  description = "Fully qualified domain name of the PostgreSQL server"
  value       = var.database_type == "postgresql" ? azurerm_postgresql_flexible_server.main[0].fqdn : null
}

output "postgres_server_name" {
  description = "Name of the PostgreSQL server"
  value       = var.database_type == "postgresql" ? azurerm_postgresql_flexible_server.main[0].name : null
}

output "postgres_database_name" {
  description = "Name of the PostgreSQL database"
  value       = var.database_type == "postgresql" ? var.postgres_database_name : null
}

output "postgres_username" {
  description = "PostgreSQL admin username"
  value       = var.database_type == "postgresql" ? var.postgres_username : null
}

output "postgres_connection_string" {
  description = "PostgreSQL connection string (password in Key Vault)"
  value       = var.database_type == "postgresql" ? "postgresql://${var.postgres_username}@${azurerm_postgresql_flexible_server.main[0].fqdn}:5432/${var.postgres_database_name}?sslmode=require" : null
  sensitive   = true
}

########################################
# N8N Configuration Outputs
########################################
output "n8n_host" {
  description = "Configured hostname for n8n"
  value       = var.n8n_host
}

output "n8n_namespace" {
  description = "Kubernetes namespace for n8n"
  value       = var.n8n_namespace
}

output "n8n_protocol" {
  description = "Protocol for n8n (http or https)"
  value       = var.n8n_protocol
}

########################################
# Log Analytics Outputs
########################################
output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.id
}

output "log_analytics_workspace_name" {
  description = "Name of the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.name
}

########################################
# Basic Auth Outputs (if enabled)
########################################
output "basic_auth_enabled" {
  description = "Whether basic authentication is enabled"
  value       = var.enable_basic_auth
}

output "basic_auth_username" {
  description = "Basic auth username (password in Key Vault)"
  value       = var.enable_basic_auth ? "admin" : null
}

########################################
# Deployment Information
########################################
output "deployment_summary" {
  description = "Summary of the deployment"
  value = {
    cluster_name        = azurerm_kubernetes_cluster.main.name
    resource_group      = azurerm_resource_group.main.name
    location            = azurerm_resource_group.main.location
    kubernetes_version  = azurerm_kubernetes_cluster.main.kubernetes_version
    database_type       = var.database_type
    ingress_enabled     = var.enable_nginx_ingress
    cert_manager        = var.enable_cert_manager
    basic_auth          = var.enable_basic_auth
    n8n_url             = var.enable_nginx_ingress ? "${var.n8n_protocol}://${var.n8n_host}" : "Configure ingress"
    key_vault_name      = azurerm_key_vault.main.name
  }
}

########################################
# Next Steps
########################################
output "next_steps" {
  description = "Next steps after Terraform deployment"
  value = <<-EOT

    ==================== DEPLOYMENT COMPLETE ====================

    1. Configure kubectl:
       az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${azurerm_kubernetes_cluster.main.name} --overwrite-existing

    2. Verify cluster access:
       kubectl get nodes
       kubectl get namespaces

    3. Access Key Vault secrets:
       az keyvault secret show --vault-name ${azurerm_key_vault.main.name} --name n8n-encryption-key
       ${var.database_type == "postgresql" ? "az keyvault secret show --vault-name ${azurerm_key_vault.main.name} --name postgres-password" : ""}

    4. Deploy n8n application:
       cd ../../../charts/n8n
       helm upgrade --install n8n . \
         --namespace ${var.n8n_namespace} \
         --create-namespace \
         --values values-azure.yaml \
         --set-string config.encryptionKey="$(az keyvault secret show --vault-name ${azurerm_key_vault.main.name} --name n8n-encryption-key --query value -o tsv)"

    5. Access n8n:
       ${var.enable_nginx_ingress ? "URL: ${var.n8n_protocol}://${var.n8n_host}" : "Configure DNS to point to: ${azurerm_public_ip.lb[0].ip_address}"}
       ${var.enable_basic_auth ? "Username: admin\n       Password: (stored in Key Vault secret 'n8n-basic-auth')" : ""}

    6. View logs:
       kubectl logs -n ${var.n8n_namespace} -l app=n8n -f

    7. Monitor with Azure Portal:
       Log Analytics Workspace: ${azurerm_log_analytics_workspace.main.name}

    ============================================================
  EOT
}
