resource "google_service_account" "signer" {
  project      = var.project_id
  account_id   = "stage-lab-signer"
  display_name = "Stage Lab signed URL service"
}

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
