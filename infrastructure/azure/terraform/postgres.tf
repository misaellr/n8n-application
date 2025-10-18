########################################
# PostgreSQL Flexible Server
# Only created when database_type = "postgresql"
########################################

# Generate PostgreSQL admin password
resource "random_password" "postgres_password" {
  count   = var.database_type == "postgresql" ? 1 : 0
  length  = 32
  special = true
}

# PostgreSQL Flexible Server
resource "azurerm_postgresql_flexible_server" "main" {
  count                  = var.database_type == "postgresql" ? 1 : 0
  name                   = "${local.project_tag}-postgres"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = var.postgres_version
  administrator_login    = var.postgres_username
  administrator_password = random_password.postgres_password[0].result
  zone                   = var.postgres_high_availability ? null : "1"

  storage_mb   = var.postgres_storage_gb * 1024
  sku_name     = var.postgres_sku
  backup_retention_days = var.postgres_backup_retention_days

  # High availability configuration
  dynamic "high_availability" {
    for_each = var.postgres_high_availability ? [1] : []
    content {
      mode = "ZoneRedundant"
    }
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-postgres"
    }
  )
}

# PostgreSQL Database
resource "azurerm_postgresql_flexible_server_database" "n8n" {
  count     = var.database_type == "postgresql" ? 1 : 0
  name      = var.postgres_database_name
  server_id = azurerm_postgresql_flexible_server.main[0].id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# PostgreSQL Firewall Rule - Allow Azure Services
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  count            = var.database_type == "postgresql" ? 1 : 0
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main[0].id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# PostgreSQL Firewall Rule - Allow AKS Subnet
# Note: For production, use Private Endpoint instead of firewall rules
resource "azurerm_postgresql_flexible_server_firewall_rule" "aks_subnet" {
  count            = var.database_type == "postgresql" ? length(local.availability_zones) : 0
  name             = "AllowAKSSubnet-${local.availability_zones[count.index]}"
  server_id        = azurerm_postgresql_flexible_server.main[0].id
  start_ip_address = cidrhost(azurerm_subnet.private[count.index].address_prefixes[0], 0)
  end_ip_address   = cidrhost(azurerm_subnet.private[count.index].address_prefixes[0], -1)
}

# PostgreSQL Configuration - SSL Enforcement
resource "azurerm_postgresql_flexible_server_configuration" "ssl_enforcement" {
  count     = var.database_type == "postgresql" ? 1 : 0
  name      = "require_secure_transport"
  server_id = azurerm_postgresql_flexible_server.main[0].id
  value     = "on"
}

# Store PostgreSQL credentials in Key Vault
resource "azurerm_key_vault_secret" "postgres_password" {
  count        = var.database_type == "postgresql" ? 1 : 0
  name         = "postgres-password"
  value        = random_password.postgres_password[0].result
  key_vault_id = azurerm_key_vault.main.id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-postgres-password"
    }
  )

  depends_on = [
    azurerm_key_vault_access_policy.terraform
  ]
}

# Store full PostgreSQL connection info in Key Vault
resource "azurerm_key_vault_secret" "postgres_connection" {
  count        = var.database_type == "postgresql" ? 1 : 0
  name         = "postgres-connection"
  key_vault_id = azurerm_key_vault.main.id

  value = jsonencode({
    host     = azurerm_postgresql_flexible_server.main[0].fqdn
    port     = 5432
    database = var.postgres_database_name
    username = var.postgres_username
    password = random_password.postgres_password[0].result
    ssl      = true
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-postgres-connection"
    }
  )

  depends_on = [
    azurerm_key_vault_access_policy.terraform
  ]
}
