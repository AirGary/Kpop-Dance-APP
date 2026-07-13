terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "api" {
  source = "../../modules/api"

  project_id      = var.project_id
  region          = var.region
  container_image = var.container_image
}

module "data" {
  source = "../../modules/data"

  project_id = var.project_id
  location   = var.location
}

module "storage" {
  source = "../../modules/storage"

  project_id         = var.project_id
  location           = var.location
  source_bucket_name = var.source_bucket_name
  result_bucket_name = var.result_bucket_name
}
