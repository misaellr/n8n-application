########################################
# AKS Cluster
########################################
resource "azurerm_kubernetes_cluster" "main" {
  name                = var.cluster_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = var.dns_prefix
  kubernetes_version  = var.kubernetes_version

  # System-assigned managed identity
  identity {
    type = "SystemAssigned"
  }

  # Default node pool
  default_node_pool {
    name                = "system"
    vm_size             = var.node_vm_size
    os_disk_size_gb     = var.node_os_disk_size_gb
    vnet_subnet_id      = azurerm_subnet.private[0].id
    # Let Azure handle zone distribution automatically for cross-region compatibility
    enable_auto_scaling = var.enable_auto_scaling
    node_count          = var.enable_auto_scaling ? null : var.node_count
    min_count           = var.enable_auto_scaling ? var.node_min_count : null
    max_count           = var.enable_auto_scaling ? var.node_max_count : null

    node_labels = {
      role        = "system"
      environment = "production"
    }

    tags = merge(
      local.common_tags,
      {
        Name = "${local.project_tag}-aks-node"
      }
    )
  }

  # Network configuration
  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure"
    load_balancer_sku = "standard"
    outbound_type     = "userAssignedNATGateway"

    # Use custom DNS service IP within the service CIDR
    service_cidr   = "10.1.0.0/16"
    dns_service_ip = "10.1.0.10"
  }

  # Add-ons
  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }

  # Azure Monitor (optional)
  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  tags = merge(
    local.common_tags,
    {
      Name = var.cluster_name
    }
  )

  depends_on = [
    azurerm_subnet_nat_gateway_association.private
  ]
}

########################################
# Log Analytics Workspace (for monitoring)
########################################
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.project_tag}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-logs"
    }
  )
}

########################################
# Role Assignments
# NOTE: These require "User Access Administrator" or "Owner" permissions
# If you get authorization errors, ask your Azure admin to run these commands manually:
#
# az role assignment create --role "Network Contributor" \
#   --assignee $(az aks show -g n8n-test-rg -n n8n-test-aks --query "identity.principalId" -o tsv) \
#   --scope /subscriptions/013c5d82-8670-4c50-81d1-1c84a77a8303/resourceGroups/n8n-test-rg
#
# az role assignment create --role "Key Vault Secrets User" \
#   --assignee $(az aks show -g n8n-test-rg -n n8n-test-aks --query "addonProfiles.azureKeyvaultSecretsProvider.identity.objectId" -o tsv) \
#   --scope $(az keyvault show -g n8n-test-rg -n n8n-test-kv-6e3377c5 --query id -o tsv)
########################################

# Commented out - requires elevated permissions
# Uncomment if you have "User Access Administrator" or "Owner" role
# resource "azurerm_role_assignment" "aks_network_contributor" {
#   scope                = azurerm_resource_group.main.id
#   role_definition_name = "Network Contributor"
#   principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
# }

# resource "azurerm_role_assignment" "aks_keyvault_secrets_user" {
#   scope                = azurerm_key_vault.main.id
#   role_definition_name = "Key Vault Secrets User"
#   principal_id         = azurerm_kubernetes_cluster.main.addonProfiles.azureKeyvaultSecretsProvider.identity.objectId
# }

########################################
# Storage Class for AKS (Azure Disk)
########################################
resource "kubernetes_storage_class" "azure_disk_premium" {
  metadata {
    name = "azure-disk-premium"
    annotations = {
      "storageclass.kubernetes.io/is-default-class" = "true"
    }
  }

  storage_provisioner    = "disk.csi.azure.com"
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true

  parameters = {
    skuName = "Premium_LRS"
    kind    = "Managed"
  }

  depends_on = [azurerm_kubernetes_cluster.main]
}
