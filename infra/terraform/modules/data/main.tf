resource "google_firebase_project" "default" {
  provider = google-beta
  project  = var.project_id
}

resource "google_identity_platform_config" "default" {
  project = var.project_id

  sign_in {
    allow_duplicate_emails = false

    anonymous {
      enabled = false
    }

    email {
      enabled           = false
      password_required = true
    }

    phone_number {
      enabled = false
    }
  }

  multi_tenant {
    allow_tenants = false
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_firebase_project.default]
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
