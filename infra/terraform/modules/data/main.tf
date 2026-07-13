resource "google_service_account" "worker" {
  project      = var.project_id
  account_id   = "stage-lab-worker"
  display_name = "Stage Lab analysis worker"
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
