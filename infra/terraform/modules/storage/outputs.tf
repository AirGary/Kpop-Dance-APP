output "source_bucket_name" {
  description = "Source-video bucket name."
  value       = google_storage_bucket.source.name
}

output "result_bucket_name" {
  description = "Analysis-result bucket name."
  value       = google_storage_bucket.result.name
}
