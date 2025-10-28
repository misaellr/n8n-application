# N8N GKE Deployment on Google Cloud Platform
# This Terraform configuration provisions:
# - VPC network with Cloud NAT for private GKE nodes
# - GKE regional cluster with workload identity
# - Service accounts with minimal IAM permissions
# - Secret Manager for encryption keys
# - Optional Cloud SQL PostgreSQL database

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

provider "google-beta" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

# Data sources
data "google_client_config" "default" {}

# Compute effective zone (use variable if provided, otherwise region-a)
locals {
  gcp_zone = var.gcp_zone != "" ? var.gcp_zone : "${var.gcp_region}-a"

  # Common labels for all resources
  common_labels = merge(
    var.labels,
    {
      cluster     = var.cluster_name
      environment = "production"
    }
  )
}
