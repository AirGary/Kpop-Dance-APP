output "api_url" {
  description = "Public Cloud Run API URL."
  value       = module.api.service_url
}

output "artifact_repository_id" {
  description = "Artifact Registry repository after a future deployment."
  value       = module.api.repository_id
}

output "runtime_service_account" {
  description = "Dedicated Cloud Run runtime service account."
  value       = module.api.runtime_service_account
}
