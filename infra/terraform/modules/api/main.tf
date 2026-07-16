resource "google_cloud_run_v2_service" "api" {
  project  = var.project_id
  location = var.region
  name     = "stage-lab-api"

  deletion_protection = true
  ingress             = "INGRESS_TRAFFIC_ALL"

  lifecycle {
    ignore_changes = [scaling]
  }

  template {
    service_account                  = var.api_service_account_email
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
        value = "cloud"
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "SOURCE_BUCKET_NAME"
        value = var.source_bucket
      }

      env {
        name  = "RESULT_BUCKET_NAME"
        value = var.result_bucket
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
          path = "/health"
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
