terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

locals {
  required_services = toset([
    "artifactregistry.googleapis.com",
    "firebase.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "identitytoolkit.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

moved {
  from = module.api.google_artifact_registry_repository.api
  to   = google_artifact_registry_repository.api
}

moved {
  from = module.api.google_service_account.api
  to   = google_service_account.api
}

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

  depends_on = [google_project_service.required]
}

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "stage-lab-api"
  display_name = "Stage Lab API"

  depends_on = [google_project_service.required]
}

module "api" {
  source = "../../modules/api"

  project_id                = var.project_id
  region                    = var.region
  container_image           = var.container_image
  source_bucket             = var.source_bucket_name
  result_bucket             = var.result_bucket_name
  api_service_account_email = google_service_account.api.email

  depends_on = [module.storage, module.data]
}

module "storage" {
  source = "../../modules/storage"

  project_id                = var.project_id
  location                  = var.region
  source_bucket_name        = var.source_bucket_name
  result_bucket_name        = var.result_bucket_name
  api_service_account_email = google_service_account.api.email

  depends_on = [google_project_service.required]
}

module "data" {
  source = "../../modules/data"

  providers = {
    google-beta = google-beta
  }

  project_id                = var.project_id
  location                  = var.region
  api_service_account_email = google_service_account.api.email

  depends_on = [google_project_service.required]
}
