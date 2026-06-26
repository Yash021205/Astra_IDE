# Infrastructure as Code (tech-stack §9: Terraform) for the cloud cluster.
# Provisions a GKE Autopilot cluster to run ASTRA-IDE (matches the "Kubernetes
# (cloud): GKE Autopilot" choice in the report). Autopilot is node-managed, so
# we only declare the cluster; workloads come from k8s/ via kubectl/Helm/Skaffold.
#
#   terraform init
#   terraform apply -var project_id=contactmanager-469218 -var region=asia-south1
#   gcloud container clusters get-credentials astra-ide --region asia-south1

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_container_cluster" "astra" {
  name             = var.cluster_name
  location         = var.region
  enable_autopilot = true

  # Autopilot manages nodes; release channel keeps the control plane current.
  release_channel {
    channel = "REGULAR"
  }

  # Private-ish defaults; tighten with authorized networks in production.
  ip_allocation_policy {}

  deletion_protection = false
}
