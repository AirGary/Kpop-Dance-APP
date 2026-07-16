variable "project_id" {
  description = "Google Cloud project that owns the development API."
  type        = string
}

variable "region" {
  description = "Regional location for the API resources."
  type        = string
}

variable "container_image" {
  description = "Immutable API image URI including its sha256 digest."
  type        = string
}

variable "api_service_account_email" {
  description = "Dedicated runtime service account created by the environment."
  type        = string
}

variable "source_bucket" {
  description = "Private source-video bucket name exposed to the API."
  type        = string
}

variable "result_bucket" {
  description = "Private analysis-result bucket name exposed to the API."
  type        = string
}
