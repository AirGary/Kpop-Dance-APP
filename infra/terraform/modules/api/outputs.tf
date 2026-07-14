output "service_url" {
  description = "Cloud Run API URL after a future deployment."
  value       = google_cloud_run_v2_service.api.uri
}

output "repository_id" {
  description = "Artifact Registry repository identifier."
  value       = google_artifact_registry_repository.api.id
}

output "runtime_service_account" {
  description = "Dedicated Cloud Run runtime service account email."
  value       = google_service_account.api.email
}
