# Secret Manager resources for encryption keys
# Stores sensitive data for n8n application:
# - N8N encryption key (required for data encryption at rest)
# - Basic auth credentials (optional, if enabled)

# Note: Due to Terraform's handling of sensitive values, encryption keys
# should be provided via terraform.tfvars rather than generated here.
# This avoids "marked value" errors during validation.

# ============================================================
# N8N Encryption Key Secret
# ============================================================

# Secret Manager secret for n8n encryption key
resource "google_secret_manager_secret" "n8n_encryption_key" {
  secret_id = "${var.cluster_name}-n8n-encryption-key"
  project   = var.gcp_project_id

  labels = merge(
    local.common_labels,
    {
      secret_type = "encryption-key"
    }
  )

  replication {
    auto {}
  }

  lifecycle {
    prevent_destroy = false # Set to true in production
  }
}

# Secret version containing the actual encryption key value
resource "google_secret_manager_secret_version" "n8n_encryption_key" {
  secret      = google_secret_manager_secret.n8n_encryption_key.id
  secret_data = var.n8n_encryption_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# Grant workload service account access to read the encryption key
resource "google_secret_manager_secret_iam_member" "n8n_encryption_key_access" {
  secret_id = google_secret_manager_secret.n8n_encryption_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.n8n_workload.email}"

  depends_on = [google_secret_manager_secret.n8n_encryption_key]
}

# ============================================================
# Basic Auth Credentials Secret (Conditional)
# ============================================================

# Secret Manager secret for basic auth credentials
resource "google_secret_manager_secret" "basic_auth" {
  count     = var.enable_basic_auth ? 1 : 0
  secret_id = "${var.cluster_name}-n8n-basic-auth"
  project   = var.gcp_project_id

  labels = merge(
    local.common_labels,
    {
      secret_type = "basic-auth"
    }
  )

  replication {
    auto {}
  }

  lifecycle {
    prevent_destroy = false # Set to true in production
  }
}

# Secret version for basic auth
# Stores username:password format
resource "google_secret_manager_secret_version" "basic_auth" {
  count       = var.enable_basic_auth ? 1 : 0
  secret      = google_secret_manager_secret.basic_auth[0].id
  secret_data = "${var.basic_auth_username}:${var.basic_auth_password}"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# Grant workload service account access to basic auth secret
resource "google_secret_manager_secret_iam_member" "basic_auth_access" {
  count     = var.enable_basic_auth ? 1 : 0
  secret_id = google_secret_manager_secret.basic_auth[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.n8n_workload.email}"

  depends_on = [google_secret_manager_secret.basic_auth]
}
