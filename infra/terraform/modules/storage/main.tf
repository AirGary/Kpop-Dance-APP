resource "google_storage_bucket" "source" {
  project                     = var.project_id
  name                        = var.source_bucket_name
  location                    = var.location
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 1
    }
  }
}

resource "google_storage_bucket_iam_member" "source_api" {
  bucket = google_storage_bucket.source.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${var.api_service_account_email}"
}

resource "google_storage_bucket" "result" {
  project                     = var.project_id
  name                        = var.result_bucket_name
  location                    = var.location
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 7
    }
  }
}

resource "google_storage_bucket_iam_member" "result_api" {
  bucket = google_storage_bucket.result.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${var.api_service_account_email}"
}
