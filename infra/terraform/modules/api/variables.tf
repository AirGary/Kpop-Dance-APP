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
