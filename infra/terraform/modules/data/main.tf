resource "google_firebase_project" "default" {
  provider = google-beta
  project  = var.project_id
}

resource "google_firestore_database" "jobs" {
  project                     = var.project_id
  name                        = "(default)"
  location_id                 = var.location
  type                        = "FIRESTORE_NATIVE"
  concurrency_mode            = "OPTIMISTIC"
  app_engine_integration_mode = "DISABLED"
  deletion_policy             = "ABANDON"
}

resource "google_project_iam_member" "api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${var.api_service_account_email}"
}

resource "google_firestore_field" "upload_expiration" {
  project    = var.project_id
  database   = google_firestore_database.jobs.name
  collection = "uploads"
  field      = "ttlExpiresAt"

  ttl_config {}
}
