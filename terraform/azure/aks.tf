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
#
# Azure Permission Requirements:
# - Network Contributor: Required for LoadBalancer services in custom VNets
#   * Needed for both static AND dynamic IP configurations
#   * Allows AKS to create/manage load balancers and attach to VNet subnets
# - Key Vault Secrets User: Required for accessing Key Vault secrets
#
# NOTE: Creating these role assignments requires "User Access Administrator" or "Owner" permissions
#
# If you get authorization errors during Terraform apply, you have two options:
#
# Option 1: Ask your Azure admin to grant you the required permissions
# Option 2: Ask your Azure admin to run these commands manually BEFORE running Terraform:
#
#    # Network Contributor (required for nginx-ingress LoadBalancer)
#    az role assignment create --role "Network Contributor" \
#      --assignee $(az aks show -g RESOURCE_GROUP -n CLUSTER_NAME --query "identity.principalId" -o tsv) \
#      --scope /subscriptions/SUBSCRIPTION_ID/resourceGroups/RESOURCE_GROUP
#
#    # Key Vault Secrets User (required for accessing secrets)
#    az role assignment create --role "Key Vault Secrets User" \
#      --assignee $(az aks show -g RESOURCE_GROUP -n CLUSTER_NAME --query "keyVaultSecretsProvider.secretIdentity.objectId" -o tsv) \
#      --scope $(az keyvault show -g RESOURCE_GROUP -n KEY_VAULT_NAME --query id -o tsv)
#
# Then disable these role assignments in Terraform by setting:
#   terraform_manage_role_assignments = false
########################################

# Network Contributor role - required for LoadBalancer services in custom VNets
# This applies to BOTH static and dynamic IP configurations
resource "azurerm_role_assignment" "aks_network_contributor" {
  count                = var.terraform_manage_role_assignments && var.enable_nginx_ingress ? 1 : 0
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id

  depends_on = [azurerm_kubernetes_cluster.main]
}

# Key Vault Secrets User role - for accessing secrets from Key Vault
resource "azurerm_role_assignment" "aks_keyvault_secrets_user" {
  count                = var.terraform_manage_role_assignments ? 1 : 0
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_kubernetes_cluster.main.key_vault_secrets_provider[0].secret_identity[0].object_id

  depends_on = [azurerm_kubernetes_cluster.main]
}

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
