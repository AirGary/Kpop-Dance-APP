variable "project_id" {
  description = "Google Cloud project ID. No default prevents accidental deployment."
  type        = string
}

variable "region" {
  description = "Singapore region used by compute resources."
  type        = string
  default     = "asia-southeast1"
}

variable "location" {
  description = "Singapore-compatible location used by data resources."
  type        = string
  default     = "asia-southeast1"
}

variable "container_image" {
  description = "Immutable API image URI supplied only during a future deployment."
  type        = string
}

variable "source_bucket_name" {
  description = "Globally unique temporary source-video bucket name."
  type        = string
}

variable "result_bucket_name" {
  description = "Globally unique temporary result bucket name."
  type        = string
}

variable "billing_budget_thresholds_usd" {
  description = "Future billing alert thresholds; Stage 2 creates no budget or resources."
  type        = list(number)
  default     = [20, 35, 50]
}
