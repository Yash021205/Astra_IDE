variable "project_id" {
  description = "GCP project ID (e.g. contactmanager-469218)"
  type        = string
}

variable "region" {
  description = "GCP region for the Autopilot cluster"
  type        = string
  default     = "asia-south1"
}

variable "cluster_name" {
  description = "GKE cluster name"
  type        = string
  default     = "astra-ide"
}
