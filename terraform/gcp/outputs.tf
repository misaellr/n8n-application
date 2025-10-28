# Terraform outputs for GCP n8n deployment
# Provides essential information needed for Kubernetes deployment and debugging

# ============================================================
# Project and Region Information
# ============================================================

output "project_id" {
  description = "GCP project ID"
  value       = var.gcp_project_id
}

output "region" {
  description = "GCP region where resources are deployed"
  value       = var.gcp_region
}

output "zone" {
  description = "GCP zone for zonal resources"
  value       = local.gcp_zone
}

# ============================================================
# VPC Networking Outputs
# ============================================================

output "vpc_name" {
  description = "Name of the VPC network"
  value       = google_compute_network.vpc.name
}

output "vpc_id" {
  description = "ID of the VPC network"
  value       = google_compute_network.vpc.id
}

output "vpc_self_link" {
  description = "Self-link of the VPC network"
  value       = google_compute_network.vpc.self_link
}

output "subnet_name" {
  description = "Name of the private subnet"
  value       = google_compute_subnetwork.private_subnet.name
}

output "subnet_cidr" {
  description = "CIDR range of the private subnet (nodes)"
  value       = google_compute_subnetwork.private_subnet.ip_cidr_range
}

output "pods_cidr" {
  description = "Secondary CIDR range for GKE pods"
  value       = google_compute_subnetwork.private_subnet.secondary_ip_range[0].ip_cidr_range
}

output "services_cidr" {
  description = "Secondary CIDR range for GKE services"
  value       = google_compute_subnetwork.private_subnet.secondary_ip_range[1].ip_cidr_range
}

output "nat_gateway_name" {
  description = "Name of the Cloud NAT gateway"
  value       = google_compute_router_nat.nat.name
}

# ============================================================
# GKE Cluster Outputs
# ============================================================

output "cluster_name" {
  description = "Name of the GKE cluster"
  value       = google_container_cluster.primary.name
}

output "cluster_id" {
  description = "ID of the GKE cluster"
  value       = google_container_cluster.primary.id
}

output "cluster_endpoint" {
  description = "Endpoint for GKE cluster API server"
  value       = google_container_cluster.primary.endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "Base64 encoded CA certificate for GKE cluster"
  value       = google_container_cluster.primary.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

output "cluster_location" {
  description = "Location (region) of the GKE cluster"
  value       = google_container_cluster.primary.location
}

output "cluster_master_version" {
  description = "Kubernetes version of the GKE cluster master"
  value       = google_container_cluster.primary.master_version
}

output "node_pool_name" {
  description = "Name of the GKE node pool"
  value       = google_container_node_pool.primary_nodes.name
}

output "node_count" {
  description = "Number of nodes in the node pool"
  value       = google_container_node_pool.primary_nodes.node_count
}

output "node_machine_type" {
  description = "Machine type for GKE nodes"
  value       = var.node_machine_type
}

# ============================================================
# Service Account Outputs
# ============================================================

output "gke_cluster_sa_email" {
  description = "Email of the GKE cluster service account"
  value       = google_service_account.gke_cluster.email
}

output "gke_nodes_sa_email" {
  description = "Email of the GKE nodes service account"
  value       = google_service_account.gke_nodes.email
}

output "n8n_workload_sa_email" {
  description = "Email of the n8n workload service account (for workload identity)"
  value       = google_service_account.n8n_workload.email
}

output "n8n_workload_sa_name" {
  description = "Name of the n8n workload service account"
  value       = google_service_account.n8n_workload.name
}

# ============================================================
# Secret Manager Outputs
# ============================================================

output "encryption_key_secret_id" {
  description = "Secret Manager secret ID for n8n encryption key"
  value       = google_secret_manager_secret.n8n_encryption_key.secret_id
}

output "encryption_key_secret_name" {
  description = "Full resource name of the encryption key secret"
  value       = google_secret_manager_secret.n8n_encryption_key.name
}

output "basic_auth_secret_id" {
  description = "Secret Manager secret ID for basic auth (null if not enabled)"
  value       = var.enable_basic_auth ? google_secret_manager_secret.basic_auth[0].secret_id : null
}

output "basic_auth_secret_name" {
  description = "Full resource name of the basic auth secret (null if not enabled)"
  value       = var.enable_basic_auth ? google_secret_manager_secret.basic_auth[0].name : null
}

# ============================================================
# Cloud SQL Outputs (Conditional)
# ============================================================

output "database_type" {
  description = "Database type (sqlite or cloudsql)"
  value       = var.database_type
}

output "cloudsql_instance_name" {
  description = "Name of the Cloud SQL instance (null if using sqlite)"
  value       = var.database_type == "cloudsql" ? google_sql_database_instance.postgres[0].name : null
}

output "cloudsql_instance_connection_name" {
  description = "Connection name for Cloud SQL instance (project:region:instance) (null if using sqlite)"
  value       = var.database_type == "cloudsql" ? google_sql_database_instance.postgres[0].connection_name : null
}

output "cloudsql_private_ip" {
  description = "Private IP address of the Cloud SQL instance (null if using sqlite)"
  value       = var.database_type == "cloudsql" ? google_sql_database_instance.postgres[0].private_ip_address : null
}

output "cloudsql_database_name" {
  description = "Name of the n8n database in Cloud SQL (null if using sqlite)"
  value       = var.database_type == "cloudsql" ? google_sql_database.n8n[0].name : null
}

output "cloudsql_database_version" {
  description = "PostgreSQL version of the Cloud SQL instance (null if using sqlite)"
  value       = var.database_type == "cloudsql" ? google_sql_database_instance.postgres[0].database_version : null
}

output "cloudsql_username" {
  description = "Database username for Cloud SQL (null if using sqlite)"
  value       = var.database_type == "cloudsql" ? var.cloudsql_username : null
}

# ============================================================
# kubectl Configuration Command
# ============================================================

output "kubectl_config_command" {
  description = "Command to configure kubectl to access the GKE cluster"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --region ${google_container_cluster.primary.location} --project ${var.gcp_project_id}"
}

# ============================================================
# Workload Identity Configuration
# ============================================================

output "workload_identity_namespace" {
  description = "Kubernetes namespace for n8n deployment"
  value       = var.n8n_namespace
}

output "workload_identity_ksa_name" {
  description = "Kubernetes service account name for n8n (must be created in k8s)"
  value       = "n8n"
}

output "workload_identity_annotation" {
  description = "Annotation to add to Kubernetes service account for workload identity"
  value       = "iam.gke.io/gcp-service-account=${google_service_account.n8n_workload.email}"
}

# ============================================================
# Summary Output
# ============================================================

output "deployment_summary" {
  description = "Summary of deployed resources"
  value = {
    project_id          = var.gcp_project_id
    region              = var.gcp_region
    cluster_name        = google_container_cluster.primary.name
    cluster_endpoint    = google_container_cluster.primary.endpoint
    node_count          = google_container_node_pool.primary_nodes.node_count
    node_machine_type   = var.node_machine_type
    database_type       = var.database_type
    vpc_name            = google_compute_network.vpc.name
    workload_sa         = google_service_account.n8n_workload.email
    n8n_namespace       = var.n8n_namespace
    kubectl_cmd         = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --region ${google_container_cluster.primary.location} --project ${var.gcp_project_id}"
  }
  sensitive = true
}
