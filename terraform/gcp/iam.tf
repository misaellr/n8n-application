# Service Accounts and IAM Role Bindings
# Creates three service accounts following least-privilege principle:
# 1. gke-cluster: For GKE control plane operations
# 2. gke-nodes: For worker node permissions
# 3. n8n-workload: For n8n pod workload identity (Secret Manager, Cloud SQL access)

# ============================================================
# Service Account Definitions
# ============================================================

# GKE Cluster Service Account
# Used by the GKE control plane for cluster operations
resource "google_service_account" "gke_cluster" {
  account_id   = "${var.cluster_name}-cluster-sa"
  display_name = "GKE Cluster Service Account for ${var.cluster_name}"
  description  = "Service account for GKE cluster control plane operations"
  project      = var.gcp_project_id
}

# GKE Node Pool Service Account
# Used by GKE worker nodes for logging, monitoring, and container registry access
resource "google_service_account" "gke_nodes" {
  account_id   = "${var.cluster_name}-nodes-sa"
  display_name = "GKE Nodes Service Account for ${var.cluster_name}"
  description  = "Service account for GKE worker nodes"
  project      = var.gcp_project_id
}

# N8N Workload Service Account
# Used by n8n pods via workload identity for Secret Manager and Cloud SQL access
resource "google_service_account" "n8n_workload" {
  account_id   = "${var.cluster_name}-n8n-sa"
  display_name = "N8N Workload Service Account"
  description  = "Service account for n8n application pods (workload identity)"
  project      = var.gcp_project_id
}

# ============================================================
# IAM Role Bindings - GKE Cluster Service Account
# ============================================================

# GKE Cluster: Service Agent role for GKE cluster operations
resource "google_project_iam_member" "gke_cluster_service_agent" {
  project = var.gcp_project_id
  role    = "roles/container.serviceAgent"
  member  = "serviceAccount:${google_service_account.gke_cluster.email}"
}

# GKE Cluster: Network User for VPC operations
resource "google_project_iam_member" "gke_cluster_network_user" {
  project = var.gcp_project_id
  role    = "roles/compute.networkUser"
  member  = "serviceAccount:${google_service_account.gke_cluster.email}"
}

# ============================================================
# IAM Role Bindings - GKE Nodes Service Account
# ============================================================

# GKE Nodes: Log Writer for writing logs to Cloud Logging
resource "google_project_iam_member" "gke_nodes_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# GKE Nodes: Metric Writer for writing metrics to Cloud Monitoring
resource "google_project_iam_member" "gke_nodes_metric_writer" {
  project = var.gcp_project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# GKE Nodes: Monitoring Viewer for reading monitoring data
resource "google_project_iam_member" "gke_nodes_monitoring_viewer" {
  project = var.gcp_project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# GKE Nodes: Artifact Registry Reader for pulling container images
resource "google_project_iam_member" "gke_nodes_artifact_registry" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# ============================================================
# IAM Role Bindings - N8N Workload Service Account
# ============================================================

# N8N Workload: Secret Manager Accessor for reading encryption keys
resource "google_project_iam_member" "n8n_workload_secret_accessor" {
  project = var.gcp_project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.n8n_workload.email}"
}

# N8N Workload: Cloud SQL Client (conditional - only if using Cloud SQL)
resource "google_project_iam_member" "n8n_workload_cloudsql_client" {
  count   = var.database_type == "cloudsql" ? 1 : 0
  project = var.gcp_project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.n8n_workload.email}"
}

# ============================================================
# Workload Identity Binding
# ============================================================

# Allow n8n Kubernetes service account to impersonate n8n workload service account
# This enables workload identity: pods running as k8s SA can assume GCP SA permissions
resource "google_service_account_iam_member" "n8n_workload_identity_binding" {
  service_account_id = google_service_account.n8n_workload.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.gcp_project_id}.svc.id.goog[${var.n8n_namespace}/n8n]"

  depends_on = [google_service_account.n8n_workload]
}
