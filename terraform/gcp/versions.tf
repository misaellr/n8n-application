terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # Backend configuration for GCS state storage
  # To use, create a GCS bucket first:
  #   gsutil mb -p PROJECT_ID -l REGION gs://BUCKET_NAME
  # Then uncomment and configure:
  # backend "gcs" {
  #   bucket = "YOUR-TERRAFORM-STATE-BUCKET"
  #   prefix = "n8n-gke/terraform/state"
  # }
}
