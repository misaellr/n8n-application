########################################
# Locals
########################################
locals {
  project_tag = var.project_tag

  # Use 3 availability zones (Azure typically has 3 zones per region)
  availability_zones = ["1", "2", "3"]

  # Regions that support PostgreSQL Flexible Server availability zones
  # Source: https://learn.microsoft.com/en-us/azure/reliability/availability-zones-service-support
  postgres_zone_supported_regions = [
    "eastus", "eastus2", "westus2", "westus3",
    "centralus", "northcentralus", "southcentralus",
    "canadacentral", "canadaeast",
    "brazilsouth",
    "northeurope", "westeurope",
    "uksouth", "ukwest",
    "francecentral",
    "germanywestcentral",
    "norwayeast",
    "switzerlandnorth",
    "swedencentral",
    "australiaeast",
    "japaneast",
    "koreacentral",
    "southeastasia",
    "eastasia",
    "southafricanorth",
    "uaenorth",
    "centralindia"
  ]

  # Smart zone selection for PostgreSQL
  # Priority: user override > auto-detect based on region > null (let Azure decide)
  postgres_zone = (
    var.postgres_availability_zone != null ? var.postgres_availability_zone :
    contains(local.postgres_zone_supported_regions, var.azure_location) && !var.postgres_high_availability ? "1" :
    null
  )

  common_tags = merge(
    {
      Project     = local.project_tag
      Environment = "production"
      ManagedBy   = "Terraform"
    },
    var.tags
  )
}

########################################
# Resource Group
########################################
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.azure_location
  tags     = local.common_tags
}

########################################
# Virtual Network
########################################
resource "azurerm_virtual_network" "main" {
  name                = "${local.project_tag}-vnet"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = [var.vnet_cidr]

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-vnet"
    }
  )
}

########################################
# Subnets
########################################
# Public subnets (for Load Balancer, NAT Gateway)
resource "azurerm_subnet" "public" {
  count                = length(local.availability_zones)
  name                 = "${local.project_tag}-public-subnet-${local.availability_zones[count.index]}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, count.index)]
}

# Private subnets (for AKS nodes)
resource "azurerm_subnet" "private" {
  count                = length(local.availability_zones)
  name                 = "${local.project_tag}-private-subnet-${local.availability_zones[count.index]}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, count.index + 100)]
}

########################################
# Public IP for NAT Gateway
########################################
resource "azurerm_public_ip" "nat" {
  name                = "${local.project_tag}-nat-pip"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  # Zone-redundant: omit zones parameter for availability across all zones

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-nat-pip"
    }
  )
}

########################################
# NAT Gateway
########################################
resource "azurerm_nat_gateway" "main" {
  name                    = "${local.project_tag}-nat-gateway"
  location                = azurerm_resource_group.main.location
  resource_group_name     = azurerm_resource_group.main.name
  sku_name                = "Standard"
  idle_timeout_in_minutes = 10
  # Zone-redundant: omit zones parameter for availability across all zones

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-nat-gateway"
    }
  )
}

# Associate NAT Gateway with Public IP
resource "azurerm_nat_gateway_public_ip_association" "main" {
  nat_gateway_id       = azurerm_nat_gateway.main.id
  public_ip_address_id = azurerm_public_ip.nat.id
}

# Associate NAT Gateway with Private Subnets
resource "azurerm_subnet_nat_gateway_association" "private" {
  count          = length(local.availability_zones)
  subnet_id      = azurerm_subnet.private[count.index].id
  nat_gateway_id = azurerm_nat_gateway.main.id
}

########################################
# Network Security Groups
########################################
# NSG for AKS nodes
resource "azurerm_network_security_group" "aks_nodes" {
  name                = "${local.project_tag}-aks-nodes-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-aks-nodes-nsg"
    }
  )
}

# Allow HTTPS inbound (for ingress)
resource "azurerm_network_security_rule" "aks_https_inbound" {
  name                        = "AllowHTTPSInbound"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.main.name
  network_security_group_name = azurerm_network_security_group.aks_nodes.name
}

# Allow HTTP inbound (for ingress)
resource "azurerm_network_security_rule" "aks_http_inbound" {
  name                        = "AllowHTTPInbound"
  priority                    = 110
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "80"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.main.name
  network_security_group_name = azurerm_network_security_group.aks_nodes.name
}

# Associate NSG with private subnets
resource "azurerm_subnet_network_security_group_association" "private" {
  count                     = length(local.availability_zones)
  subnet_id                 = azurerm_subnet.private[count.index].id
  network_security_group_id = azurerm_network_security_group.aks_nodes.id
}

########################################
# Public IPs for Load Balancer
########################################
resource "azurerm_public_ip" "lb" {
  count               = var.enable_nginx_ingress && var.use_static_ip ? 1 : 0
  name                = "${local.project_tag}-lb-pip"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  # Zone-redundant: omit zones parameter for availability across all zones

  tags = merge(
    local.common_tags,
    {
      Name = "${local.project_tag}-lb-pip"
      Purpose = "Static LoadBalancer IP (requires Network Contributor role)"
    }
  )
}
