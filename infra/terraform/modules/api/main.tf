resource "google_artifact_registry_repository" "api" {
  project                = var.project_id
  location               = var.region
  repository_id          = "stage-lab-api"
  format                 = "DOCKER"
  description            = "Stage Lab API container images"
  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "delete-untagged-after-seven-days"
    action = "DELETE"

    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"
    }
  }
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
    service_account                  = google_service_account.api.email
    timeout                          = "30s"
    max_instance_request_concurrency = 20

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.container_image

      env {
        name  = "APP_ENVIRONMENT"
        value = "cloud-bootstrap"
      }

      resources {
        cpu_idle          = true
        startup_cpu_boost = false
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      startup_probe {
        initial_delay_seconds = 0
        timeout_seconds       = 2
        period_seconds        = 3
        failure_threshold     = 10

        http_get {
          path = "/healthz"
        }
      }
    }
  }
}

resource "google_cloud_run_service_iam_member" "public" {
  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  service  = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
