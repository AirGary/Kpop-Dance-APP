output "service_url" {
  description = "Cloud Run API URL after a future deployment."
  value       = google_cloud_run_v2_service.api.uri
}

output "runtime_service_account" {
  description = "Dedicated Cloud Run runtime service account email."
  value       = var.api_service_account_email
}
