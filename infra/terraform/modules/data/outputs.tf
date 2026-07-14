output "firestore_database_name" {
  description = "Firestore database resource name."
  value       = google_firestore_database.jobs.name
}
