variable "project_id" {
  description = "Google Cloud project that owns development object storage."
  type        = string
}

variable "location" {
  description = "Regional bucket location."
  type        = string
}

variable "source_bucket_name" {
  description = "Globally unique bucket for temporary source videos."
  type        = string
}

variable "result_bucket_name" {
  description = "Globally unique bucket for temporary analysis results."
  type        = string
}
