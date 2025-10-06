variable "aws_profile" {
  description = "The AWS CLI profile to use for deployment. Configure your profile using 'aws configure --profile <your-profile-name>'."
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_tag" {
  description = "Project tag for resource naming"
  type        = string
  default     = "n8n-app"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "n8n-eks-cluster"
}

variable "cluster_version" {
  description = "Kubernetes version for EKS cluster"
  type        = string
  default     = "1.29"
}

variable "node_instance_types" {
  description = "EC2 instance types for EKS node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 1
}

variable "node_min_size" {
  description = "Minimum number of worker nodes"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of worker nodes"
  type        = number
  default     = 2
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "n8n_encryption_key" {
  description = "64 hex chars (openssl rand -hex 32). If blank, one is generated."
  type        = string
  default     = ""
  sensitive   = true
}

variable "enable_nginx_ingress" {
  description = "Whether to install nginx ingress controller via Helm"
  type        = bool
  default     = true
}

variable "n8n_namespace" {
  description = "Namespace where n8n will be installed"
  type        = string
  default     = "n8n"
}

variable "n8n_service_type" {
  description = "Service type for the n8n Service"
  type        = string
  default     = "ClusterIP"
}

variable "n8n_service_port" {
  description = "Service port exposed by n8n"
  type        = number
  default     = 5678
}

variable "n8n_host" {
  description = "Primary hostname for n8n ingress and application URLs"
  type        = string
  default     = "n8n.example.com"
}

variable "n8n_protocol" {
  description = "Protocol used to access n8n"
  type        = string
  default     = "https"
}

variable "n8n_proxy_hops" {
  description = "Number of proxy hops in front of n8n for trusted headers"
  type        = number
  default     = 1
}

variable "n8n_webhook_url" {
  description = "Optional override for the webhook URL"
  type        = string
  default     = null
}

variable "n8n_ingress_enabled" {
  description = "Whether to expose n8n via an ingress resource"
  type        = bool
  default     = true
}

variable "n8n_ingress_class" {
  description = "IngressClass name used by n8n"
  type        = string
  default     = "nginx"
}

variable "n8n_ingress_annotations" {
  description = "Annotations applied to the n8n ingress"
  type        = map(string)
  default = {
    "nginx.ingress.kubernetes.io/proxy-body-size"    = "20m"
    "nginx.ingress.kubernetes.io/proxy-read-timeout" = "600"
  }
}

variable "n8n_tls_enabled" {
  description = "Whether TLS should be enabled on the ingress"
  type        = bool
  default     = true
}

variable "n8n_tls_secret_name" {
  description = "Name of the TLS secret referenced by the ingress"
  type        = string
  default     = "n8n-tls"
}

variable "tls_certificate_source" {
  description = "TLS certificate source: 'none', 'byo' (bring your own), or 'letsencrypt'"
  type        = string
  default     = "none"
  validation {
    condition     = contains(["none", "byo", "letsencrypt"], var.tls_certificate_source)
    error_message = "tls_certificate_source must be 'none', 'byo', or 'letsencrypt'"
  }
}

variable "tls_certificate_crt" {
  description = "TLS certificate content in PEM format (for byo option)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "tls_certificate_key" {
  description = "TLS private key content in PEM format (for byo option)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "letsencrypt_email" {
  description = "Email address for Let's Encrypt certificate notifications"
  type        = string
  default     = ""
}

variable "letsencrypt_environment" {
  description = "Let's Encrypt environment: 'staging' or 'production'"
  type        = string
  default     = "production"
  validation {
    condition     = contains(["staging", "production"], var.letsencrypt_environment)
    error_message = "letsencrypt_environment must be 'staging' or 'production'"
  }
}

variable "enable_cert_manager" {
  description = "Whether to install cert-manager (required for Let's Encrypt)"
  type        = bool
  default     = false
}

variable "cert_manager_version" {
  description = "cert-manager Helm chart version"
  type        = string
  default     = "v1.13.3"
}

variable "timezone" {
  description = "Timezone for n8n (IANA format, e.g., America/New_York)"
  type        = string
  default     = "America/Bahia"
}

variable "n8n_persistence_enabled" {
  description = "Enable persistence for the n8n data directory"
  type        = bool
  default     = true
}

variable "n8n_persistence_size" {
  description = "Requested size for the n8n PersistentVolumeClaim"
  type        = string
  default     = "10Gi"
}

variable "n8n_persistence_storage_class" {
  description = "StorageClass used by the n8n PersistentVolumeClaim (empty for default)"
  type        = string
  default     = ""
}

variable "n8n_persistence_access_modes" {
  description = "Access modes for the n8n PersistentVolumeClaim"
  type        = list(string)
  default     = ["ReadWriteOnce"]
}

variable "n8n_env_overrides" {
  description = "Additional environment variables merged into n8n deployment"
  type        = map(string)
  default     = {}
}

########################################
# Database Configuration
########################################
variable "database_type" {
  description = "Database backend for n8n: 'sqlite' (default, file-based) or 'postgresql' (RDS)"
  type        = string
  default     = "sqlite"
  validation {
    condition     = contains(["sqlite", "postgresql"], var.database_type)
    error_message = "database_type must be 'sqlite' or 'postgresql'"
  }
}

variable "rds_instance_class" {
  description = "RDS instance class (only used when database_type = postgresql)"
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage" {
  description = "RDS allocated storage in GB (only used when database_type = postgresql)"
  type        = number
  default     = 20
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ deployment for RDS (only used when database_type = postgresql)"
  type        = bool
  default     = false
}

variable "rds_database_name" {
  description = "Database name for RDS PostgreSQL"
  type        = string
  default     = "n8n"
}

variable "rds_username" {
  description = "Master username for RDS PostgreSQL"
  type        = string
  default     = "n8n_user"
}

########################################
# Basic Authentication Configuration
########################################
variable "enable_basic_auth" {
  description = "Enable basic authentication for n8n ingress"
  type        = bool
  default     = false
}
