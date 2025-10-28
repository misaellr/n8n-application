variable "gcp_project_id" {
  description = "GCP Project ID where resources will be created"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.gcp_project_id))
    error_message = "Project ID must be 6-30 characters, start with a letter, and contain only lowercase letters, numbers, and hyphens."
  }
}

variable "gcp_region" {
  description = "GCP region for regional resources (cluster, Cloud NAT)"
  type        = string
  default     = "us-central1"

  validation {
    condition = contains([
      "us-central1", "us-east1", "us-west1", "us-west2",
      "europe-west1", "europe-west2", "europe-west3",
      "asia-southeast1", "asia-east1", "asia-northeast1"
    ], var.gcp_region)
    error_message = "Region must be a valid GCP region."
  }
}

variable "gcp_zone" {
  description = "GCP zone for zonal resources (defaults to {region}-a)"
  type        = string
  default     = ""
}

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "n8n-gke-cluster"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,39}$", var.cluster_name))
    error_message = "Cluster name must start with a letter, be lowercase, and contain only letters, numbers, and hyphens (max 40 chars)."
  }
}

variable "node_machine_type" {
  description = "GCE machine type for GKE worker nodes"
  type        = string
  default     = "e2-medium"

  validation {
    condition = contains([
      "e2-micro", "e2-small", "e2-medium", "e2-standard-2", "e2-standard-4",
      "n1-standard-1", "n1-standard-2", "n1-standard-4",
      "n2-standard-2", "n2-standard-4"
    ], var.node_machine_type)
    error_message = "Machine type must be a valid e2, n1, or n2 series type."
  }
}

variable "node_count" {
  description = "Number of worker nodes in the GKE cluster"
  type        = number
  default     = 1

  validation {
    condition     = var.node_count >= 1 && var.node_count <= 10
    error_message = "Node count must be between 1 and 10."
  }
}

variable "vpc_name" {
  description = "Name of the VPC network"
  type        = string
  default     = "n8n-vpc"
}

variable "subnet_name" {
  description = "Name of the subnet for GKE nodes"
  type        = string
  default     = "n8n-subnet"
}

variable "database_type" {
  description = "Database backend: 'sqlite' or 'cloudsql'"
  type        = string
  default     = "sqlite"

  validation {
    condition     = contains(["sqlite", "cloudsql"], var.database_type)
    error_message = "Database type must be either 'sqlite' or 'cloudsql'."
  }
}

variable "cloudsql_tier" {
  description = "Cloud SQL machine tier (only used if database_type='cloudsql')"
  type        = string
  default     = "db-f1-micro"

  validation {
    condition = contains([
      "db-f1-micro", "db-g1-small",
      "db-n1-standard-1", "db-n1-standard-2", "db-n1-standard-4"
    ], var.cloudsql_tier)
    error_message = "Cloud SQL tier must be a valid tier."
  }
}

variable "cloudsql_instance_name" {
  description = "Name of the Cloud SQL instance (only used if database_type='cloudsql')"
  type        = string
  default     = "n8n-postgres"
}

variable "n8n_encryption_key" {
  description = "N8N encryption key (64 hex chars). If empty, one will be generated."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition     = var.n8n_encryption_key == "" || can(regex("^[0-9a-fA-F]{64}$", var.n8n_encryption_key))
    error_message = "Encryption key must be empty or 64 hexadecimal characters."
  }
}

variable "enable_basic_auth" {
  description = "Enable basic authentication for n8n"
  type        = bool
  default     = false
}

variable "basic_auth_username" {
  description = "Basic auth username (only used if enable_basic_auth=true)"
  type        = string
  default     = "admin"
}

variable "basic_auth_password" {
  description = "Basic auth password (only used if enable_basic_auth=true)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "n8n_namespace" {
  description = "Kubernetes namespace for n8n deployment"
  type        = string
  default     = "n8n"
}

variable "labels" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default = {
    managed_by  = "terraform"
    application = "n8n"
  }
}
