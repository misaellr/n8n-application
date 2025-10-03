variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "cloud-native-misael"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "domain" {
  description = "Optional FQDN (e.g., n8n.example.com). If empty, site is served on http://<public-ip>"
  type        = string
  default     = ""
}

variable "instance_type" {
  description = "EC2 instance size"
  type        = string
  default     = "t3.small" # use t3.micro if you want the absolute cheapest
}

variable "timezone" {
  description = "Timezone for n8n and container clock"
  type        = string
  default     = "America/Bahia"
}

variable "n8n_encryption_key" {
  description = "64 hex chars (openssl rand -hex 32). If blank, one is generated."
  type        = string
  default     = ""
  sensitive   = true
}

variable "project_tag" {
  description = "Project tag for resource naming"
  type        = string
  default     = "n8n-app"
}
