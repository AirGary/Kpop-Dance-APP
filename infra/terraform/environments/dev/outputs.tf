output "api_url" {
  description = "Cloud Run URL after a future deployment."
  value       = module.api.service_url
}

output "artifact_repository_id" {
  description = "Artifact Registry repository after a future deployment."
  value       = module.api.repository_id
}

output "configured_budget_thresholds_usd" {
  description = "Threshold values reserved for the future billing-budget stage."
  value       = var.billing_budget_thresholds_usd
}
