# VPC Network and Cloud NAT configuration
# Creates VPC-native networking for GKE with:
# - Custom VPC network
# - Private subnet for GKE nodes with secondary IP ranges for pods and services
# - Cloud Router for dynamic routing
# - Cloud NAT for outbound internet access from private nodes

# VPC Network
resource "google_compute_network" "vpc" {
  name                    = var.vpc_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
  project                 = var.gcp_project_id

  description = "VPC network for n8n GKE cluster"
}

# Subnet for GKE nodes with secondary IP ranges for pods and services
# VPC-native cluster requirement: must have secondary IP ranges
resource "google_compute_subnetwork" "private_subnet" {
  name          = var.subnet_name
  ip_cidr_range = "10.0.0.0/20" # Primary range for nodes (4,096 IPs)
  region        = var.gcp_region
  network       = google_compute_network.vpc.id
  project       = var.gcp_project_id

  description = "Private subnet for GKE nodes with secondary ranges for pods and services"

  # Enable private Google access for GCP API access without public IPs
  private_ip_google_access = true

  # Secondary IP ranges for VPC-native GKE cluster
  secondary_ip_range {
    range_name    = "gke-pods"
    ip_cidr_range = "10.4.0.0/14" # Pod range (262,144 IPs)
  }

  secondary_ip_range {
    range_name    = "gke-services"
    ip_cidr_range = "10.0.16.0/20" # Service range (4,096 IPs)
  }

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Cloud Router for NAT gateway
resource "google_compute_router" "router" {
  name    = "${var.cluster_name}-router"
  region  = var.gcp_region
  network = google_compute_network.vpc.id
  project = var.gcp_project_id

  description = "Cloud Router for Cloud NAT"

  bgp {
    asn = 64514
  }
}

# Cloud NAT for outbound internet access from private GKE nodes
# Required for:
# - Pulling container images from public registries
# - Accessing external APIs
# - Cluster addons that require internet access
resource "google_compute_router_nat" "nat" {
  name                               = "${var.cluster_name}-nat"
  router                             = google_compute_router.router.name
  region                             = var.gcp_region
  project                            = var.gcp_project_id
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
