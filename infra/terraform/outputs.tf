output "cluster_name" {
  value = google_container_cluster.astra.name
}

output "cluster_endpoint" {
  value     = google_container_cluster.astra.endpoint
  sensitive = true
}

output "get_credentials_command" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.astra.name} --region ${var.region} --project ${var.project_id}"
}
