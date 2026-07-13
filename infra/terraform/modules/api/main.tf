resource "google_artifact_registry_repository" "api" {
  project       = var.project_id
  location      = var.region
  repository_id = "stage-lab-api"
  format        = "DOCKER"
  description   = "Stage Lab API container images"
}

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "stage-lab-api"
  display_name = "Stage Lab API"
}

resource "google_cloud_run_v2_service" "api" {
  project  = var.project_id
  location = var.region
  name     = "stage-lab-api"

  deletion_protection = true
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }
}
