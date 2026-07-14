variable "project_id" {
  description = "Google Cloud project ID. No default prevents accidental deployment."
  type        = string
}

variable "region" {
  description = "Singapore region used by compute resources."
  type        = string
  default     = "asia-southeast1"
}

variable "container_image" {
  description = "Immutable Artifact Registry API image URI including its sha256 digest."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.container_image))
    error_message = "container_image must use an immutable sha256 digest."
  }
}
