output "api_url" {
  description = "Public Cloud Run API URL."
  value       = module.api.service_url
}

output "artifact_repository_id" {
  description = "Artifact Registry repository after a future deployment."
  value       = google_artifact_registry_repository.api.id
}

output "runtime_service_account" {
  description = "Dedicated Cloud Run runtime service account."
  value       = google_service_account.api.email
}

output "source_bucket_name" {
  description = "Private temporary source-video bucket."
  value       = module.storage.source_bucket_name
}

output "result_bucket_name" {
  description = "Private temporary analysis-result bucket."
  value       = module.storage.result_bucket_name
}

output "firestore_database_name" {
  description = "Firestore database used for cloud metadata."
  value       = module.data.firestore_database_name
}
