########################################
# Current Azure Client Data
########################################
data "azurerm_client_config" "current" {}

########################################
# Random Suffix for Key Vault Name
########################################
resource "random_id" "keyvault_suffix" {
  byte_length = 4
}

########################################
# Azure Key Vault
########################################
resource "azurerm_key_vault" "main" {
  name                        = "${local.project_tag}-kv-${random_id.keyvault_suffix.hex}"
  location                    = azurerm_resource_group.main.location
  resource_group_name         = azurerm_resource_group.main.name
  enabled_for_disk_encryption = true
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days  = var.keyvault_soft_delete_retention_days
  purge_protection_enabled    = false
  sku_name                    = var.keyvault_sku

  # Network rules (allow all for now, can be restricted)
  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-keyvault"
    }
  )
}

########################################
# Key Vault Access Policy for Current User/Service Principal
########################################
resource "azurerm_key_vault_access_policy" "terraform" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = [
    "Get",
    "List",
    "Set",
    "Delete",
    "Purge",
    "Recover"
  ]
}

########################################
# Key Vault Access Policy for AKS
########################################
# This is configured via RBAC assignment in aks.tf
# azurerm_role_assignment.aks_keyvault_secrets_user

########################################
# Generate Encryption Key
########################################
resource "random_id" "encryption_key" {
  byte_length = 32
}

locals {
  # Use provided key if non-empty, otherwise generate random key
  encryption_key = var.n8n_encryption_key != "" ? var.n8n_encryption_key : random_id.encryption_key.hex
  n8n_host_raw   = trimspace(var.n8n_host)
  n8n_host       = local.n8n_host_raw != "" ? local.n8n_host_raw : format("%s.local", var.project_tag)
  n8n_protocol   = lower(var.n8n_protocol)
  n8n_webhook_url = coalesce(
    var.n8n_webhook_url,
    format("%s://%s/", local.n8n_protocol, local.n8n_host)
  )

  # Environment variables for n8n
  n8n_env = merge({
    N8N_HOST         = local.n8n_host
    N8N_PROTOCOL     = local.n8n_protocol
    N8N_PORT         = tostring(var.n8n_service_port)
    WEBHOOK_URL      = local.n8n_webhook_url
    N8N_PROXY_HOPS   = tostring(var.n8n_proxy_hops)
    GENERIC_TIMEZONE = var.timezone
  }, var.n8n_env_overrides)
}

########################################
# Store N8N Encryption Key in Key Vault
########################################
resource "azurerm_key_vault_secret" "n8n_encryption_key" {
  name         = "n8n-encryption-key"
  value        = local.encryption_key
  key_vault_id = azurerm_key_vault.main.id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-n8n-encryption-key"
    }
  )

  depends_on = [
    azurerm_key_vault_access_policy.terraform
  ]
}

########################################
# Store Basic Auth Credentials (if enabled)
########################################
resource "random_password" "basic_auth_password" {
  count   = var.enable_basic_auth ? 1 : 0
  length  = 12
  special = false
}

resource "azurerm_key_vault_secret" "basic_auth" {
  count        = var.enable_basic_auth ? 1 : 0
  name         = "n8n-basic-auth"
  key_vault_id = azurerm_key_vault.main.id

  value = jsonencode({
    username = "admin"
    password = random_password.basic_auth_password[0].result
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-basic-auth"
    }
  )

  depends_on = [
    azurerm_key_vault_access_policy.terraform
  ]
}
