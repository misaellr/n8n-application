########################################
# Azure Configuration
########################################
variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "azure_location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "n8n-rg"
}

variable "project_tag" {
  description = "Project tag for resource naming"
  type        = string
  default     = "n8n-app"
}

########################################
# Virtual Network Configuration
########################################
variable "vnet_cidr" {
  description = "CIDR block for the VNet"
  type        = string
  default     = "10.0.0.0/16"
}

########################################
# AKS Cluster Configuration
########################################
variable "cluster_name" {
  description = "Name of the AKS cluster"
  type        = string
  default     = "n8n-aks-cluster"
}

variable "kubernetes_version" {
  description = "Kubernetes version for AKS"
  type        = string
  default     = "1.31.11"
}

variable "dns_prefix" {
  description = "DNS prefix for the AKS cluster"
  type        = string
  default     = "n8n-aks"
}

########################################
# Node Pool Configuration
########################################
variable "node_vm_size" {
  description = "VM size for AKS node pool"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "node_count" {
  description = "Initial number of nodes"
  type        = number
  default     = 2
}

variable "node_min_count" {
  description = "Minimum number of nodes (for autoscaling)"
  type        = number
  default     = 1
}

variable "node_max_count" {
  description = "Maximum number of nodes (for autoscaling)"
  type        = number
  default     = 5
}

variable "enable_auto_scaling" {
  description = "Enable cluster autoscaler"
  type        = bool
  default     = true
}

variable "node_os_disk_size_gb" {
  description = "OS disk size in GB for nodes"
  type        = number
  default     = 128
}

########################################
# Application Configuration
########################################
variable "n8n_host" {
  description = "Hostname for n8n ingress"
  type        = string
  default     = "n8n.example.com"
}

variable "n8n_namespace" {
  description = "Kubernetes namespace for n8n"
  type        = string
  default     = "n8n"
}

variable "n8n_protocol" {
  description = "Protocol for n8n (http or https)"
  type        = string
  default     = "http"
}

variable "n8n_service_port" {
  description = "Service port for n8n"
  type        = number
  default     = 5678
}

variable "n8n_persistence_size" {
  description = "Size of persistent volume for n8n data"
  type        = string
  default     = "10Gi"
}

variable "timezone" {
  description = "Timezone for n8n"
  type        = string
  default     = "America/Bahia"
}

variable "n8n_encryption_key" {
  description = "Encryption key for n8n (64-character hex). If empty, will be auto-generated."
  type        = string
  default     = ""
}

variable "n8n_webhook_url" {
  description = "Webhook URL for n8n (optional, auto-generated if empty)"
  type        = string
  default     = ""
}

variable "n8n_proxy_hops" {
  description = "Number of proxy hops for n8n"
  type        = number
  default     = 1
}

variable "n8n_env_overrides" {
  description = "Additional environment variable overrides for n8n"
  type        = map(string)
  default     = {}
}

########################################
# Database Configuration
########################################
variable "database_type" {
  description = "Database type: sqlite or postgresql"
  type        = string
  default     = "sqlite"

  validation {
    condition     = contains(["sqlite", "postgresql"], var.database_type)
    error_message = "Database type must be either 'sqlite' or 'postgresql'."
  }
}

variable "postgres_sku" {
  description = "PostgreSQL SKU (e.g., B_Standard_B1ms, GP_Standard_D2s_v3)"
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_gb" {
  description = "PostgreSQL storage size in GB"
  type        = number
  default     = 32
}

variable "postgres_high_availability" {
  description = "Enable zone redundancy for PostgreSQL"
  type        = bool
  default     = false
}

variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "15"
}

variable "postgres_database_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "n8n"
}

variable "postgres_username" {
  description = "PostgreSQL admin username"
  type        = string
  default     = "n8nadmin"
}

variable "postgres_backup_retention_days" {
  description = "PostgreSQL backup retention in days"
  type        = number
  default     = 7
}

variable "postgres_availability_zone" {
  description = "Availability zone for PostgreSQL (null for no zone, '1', '2', or '3' for specific zone). If null, Azure auto-selects based on region capabilities."
  type        = string
  default     = null
}

########################################
# Optional Features
########################################
variable "use_static_ip" {
  description = "Use pre-allocated static IP for LoadBalancer (requires Network Contributor role). If false, Azure assigns dynamic IP."
  type        = bool
  default     = false
}

variable "enable_nginx_ingress" {
  description = "Enable NGINX ingress controller"
  type        = bool
  default     = true
}

variable "enable_basic_auth" {
  description = "Enable basic authentication for ingress"
  type        = bool
  default     = false
}

variable "enable_cert_manager" {
  description = "Install cert-manager for automatic TLS certificates"
  type        = bool
  default     = false
}

variable "terraform_manage_role_assignments" {
  description = "Let Terraform manage Azure role assignments (requires User Access Administrator or Owner permissions). Set to false if role assignments will be created manually."
  type        = bool
  default     = true
}

########################################
# Key Vault Configuration
########################################
variable "keyvault_sku" {
  description = "SKU for Azure Key Vault"
  type        = string
  default     = "standard"

  validation {
    condition     = contains(["standard", "premium"], var.keyvault_sku)
    error_message = "Key Vault SKU must be either 'standard' or 'premium'."
  }
}

variable "keyvault_soft_delete_retention_days" {
  description = "Soft delete retention period for Key Vault"
  type        = number
  default     = 7
}

########################################
# Tags
########################################
variable "tags" {
  description = "Additional tags for all resources"
  type        = map(string)
  default     = {}
}
