# Cloud SQL PostgreSQL configuration (conditional)
# Only created when var.database_type == "cloudsql"
# Provides managed PostgreSQL database with:
# - Private IP connectivity to GKE cluster
# - Automatic backups and point-in-time recovery
# - High availability option
# - Cloud SQL Proxy for secure connections via workload identity

# ============================================================
# Cloud SQL Instance
# ============================================================

# Cloud SQL PostgreSQL instance with private IP
resource "google_sql_database_instance" "postgres" {
  count            = var.database_type == "cloudsql" ? 1 : 0
  name             = "${var.cluster_name}-postgres"
  database_version = var.cloudsql_database_version
  region           = var.gcp_region
  project          = var.gcp_project_id

  settings {
    tier              = var.cloudsql_tier
    availability_type = var.cloudsql_availability_type
    disk_type         = "PD_SSD"
    disk_size         = var.cloudsql_disk_size
    disk_autoresize   = true

    # Backup configuration
    backup_configuration {
      enabled                        = true
      start_time                     = "03:00" # 3 AM UTC
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 30
        retention_unit   = "COUNT"
      }
    }

    # Maintenance window
    maintenance_window {
      day          = 7 # Sunday
      hour         = 3 # 3 AM UTC
      update_track = "stable"
    }

    # IP configuration - private IP only
    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.vpc.id
      enable_private_path_for_google_cloud_services = true
      require_ssl                                   = false # Cloud SQL Proxy provides encryption
    }

    # Database flags for PostgreSQL optimization
    database_flags {
      name  = "max_connections"
      value = "100"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    # Insights configuration for query performance monitoring
    insights_config {
      query_insights_enabled  = true
      query_plans_per_minute  = 5
      query_string_length     = 1024
      record_application_tags = true
    }

    # User labels
    user_labels = local.common_labels
  }

  deletion_protection = false # Set to true in production

  depends_on = [
    google_compute_network.vpc,
    google_service_networking_connection.private_vpc_connection
  ]
}

# ============================================================
# Private Service Connection
# ============================================================

# Reserve IP address range for private service connection
resource "google_compute_global_address" "private_ip_address" {
  count         = var.database_type == "cloudsql" ? 1 : 0
  name          = "${var.cluster_name}-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
  project       = var.gcp_project_id
}

# Create private VPC connection for Cloud SQL
# NOTE: This must be deleted AFTER Cloud SQL instance is fully removed
# If destroy fails with "Producer services still using this connection",
# manually delete Cloud SQL first: gcloud sql instances delete <instance-name>
resource "google_service_networking_connection" "private_vpc_connection" {
  count                   = var.database_type == "cloudsql" ? 1 : 0
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address[0].name]

  deletion_policy         = "ABANDON"  # Don't fail destroy if connection still in use

  depends_on = [google_compute_global_address.private_ip_address]
}

# ============================================================
# Database and User
# ============================================================

# Generate secure random password for Cloud SQL
resource "random_password" "cloudsql_password" {
  count            = var.database_type == "cloudsql" ? 1 : 0
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Create n8n database
resource "google_sql_database" "n8n" {
  count     = var.database_type == "cloudsql" ? 1 : 0
  name      = "n8n"
  instance  = google_sql_database_instance.postgres[0].name
  project   = var.gcp_project_id
  charset   = "UTF8"
  collation = "en_US.UTF8"

  depends_on = [google_sql_database_instance.postgres]
}

# Create n8n database user with auto-generated password
resource "google_sql_user" "n8n" {
  count    = var.database_type == "cloudsql" ? 1 : 0
  name     = var.cloudsql_username
  instance = google_sql_database_instance.postgres[0].name
  project  = var.gcp_project_id
  password = random_password.cloudsql_password[0].result

  depends_on = [google_sql_database_instance.postgres]
}

# Optional: Create IAM-based database user for workload identity
# Uncomment if you want to use IAM authentication instead of password
# resource "google_sql_user" "n8n_iam" {
#   count    = var.database_type == "cloudsql" ? 1 : 0
#   name     = google_service_account.n8n_workload.email
#   instance = google_sql_database_instance.postgres[0].name
#   project  = var.gcp_project_id
#   type     = "CLOUD_IAM_SERVICE_ACCOUNT"
#
#   depends_on = [
#     google_sql_database_instance.postgres,
#     google_service_account.n8n_workload
#   ]
# }
