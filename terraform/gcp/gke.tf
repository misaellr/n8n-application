# GKE Cluster and Node Pool configuration
# Creates a regional GKE cluster with:
# - Workload identity enabled for secure GCP service access
# - VPC-native networking with IP aliasing
# - Private nodes (no external IPs)
# - Network policy enabled (Calico)
# - Fixed-size node pool (no autoscaling for cost predictability)

# GKE Regional Cluster
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.gcp_region
  project  = var.gcp_project_id

  # Remove default node pool immediately (we create our own below)
  remove_default_node_pool = true
  initial_node_count       = 1

  # Network configuration
  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.private_subnet.id

  # Workload Identity configuration
  # Enables pods to authenticate as GCP service accounts
  workload_identity_config {
    workload_pool = "${var.gcp_project_id}.svc.id.goog"
  }

  # VPC-native cluster (IP aliasing)
  # Required for workload identity and provides better networking
  ip_allocation_policy {
    cluster_secondary_range_name  = "gke-pods"
    services_secondary_range_name = "gke-services"
  }

  # Private cluster configuration
  # Nodes have only private IPs, master is accessible via private endpoint
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false # Keep public endpoint for kubectl access
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Master authorized networks - allow all for initial setup
  # In production, restrict to specific IP ranges
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = "0.0.0.0/0"
      display_name = "All networks (update in production)"
    }
  }

  # Network policy configuration (Calico)
  network_policy {
    enabled  = true
    provider = "CALICO"
  }

  # Enable required addons
  addons_config {
    http_load_balancing {
      disabled = false
    }

    horizontal_pod_autoscaling {
      disabled = false
    }

    network_policy_config {
      disabled = false
    }

    # GKE DNS cache improves DNS performance
    dns_cache_config {
      enabled = true
    }
  }

  # Maintenance window configuration
  # Maintenance occurs during specified window
  maintenance_policy {
    daily_maintenance_window {
      start_time = "03:00" # 3 AM UTC
    }
  }

  # Release channel for automatic updates
  # REGULAR provides balance between stability and new features
  release_channel {
    channel = "REGULAR"
  }

  # Logging and monitoring configuration
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]

    managed_prometheus {
      enabled = true
    }
  }

  # Resource labels
  resource_labels = local.common_labels

  # Enable Binary Authorization (optional, disabled by default)
  binary_authorization {
    evaluation_mode = "DISABLED"
  }

  # Deletion protection (set to false for development, true for production)
  deletion_protection = false

  # Lifecycle configuration
  lifecycle {
    ignore_changes = [
      # Ignore node pool changes as we manage it separately
      node_pool,
      initial_node_count,
    ]
  }

  depends_on = [
    google_compute_subnetwork.private_subnet,
    google_service_account.gke_cluster,
  ]
}

# Managed Node Pool
# Separate node pool with custom configuration
resource "google_container_node_pool" "primary_nodes" {
  name       = "${var.cluster_name}-node-pool"
  location   = var.gcp_region
  cluster    = google_container_cluster.primary.name
  project    = var.gcp_project_id
  node_count = var.node_count

  # Node pool configuration
  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = 50
    disk_type    = "pd-standard"

    # Service account for nodes
    service_account = google_service_account.gke_nodes.email

    # OAuth scopes - using cloud-platform for full API access
    # Actual permissions controlled by service account IAM roles
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    # Workload identity configuration for nodes
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Metadata to disable legacy metadata endpoints
    metadata = {
      disable-legacy-endpoints = "true"
    }

    # Resource labels
    labels = merge(
      local.common_labels,
      {
        node_pool = "${var.cluster_name}-node-pool"
      }
    )

    # Tags for firewall rules
    tags = ["gke-node", var.cluster_name]

    # Shielded instance configuration for additional security
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    # Enable GCE confidential computing (optional, may increase cost)
    # confidential_nodes {
    #   enabled = true
    # }
  }

  # Node pool management
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  # Upgrade settings
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  # Lifecycle configuration
  lifecycle {
    ignore_changes = [
      # Ignore initial_node_count changes
      initial_node_count,
    ]
  }

  depends_on = [
    google_container_cluster.primary,
    google_service_account.gke_nodes,
  ]
}
