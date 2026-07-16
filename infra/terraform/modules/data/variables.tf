variable "project_id" {
  description = "Google Cloud project that owns the development database."
  type        = string
}

variable "location" {
  description = "Firestore regional location."
  type        = string
}

variable "api_service_account_email" {
  description = "Cloud Run API service account granted Firestore data access."
  type        = string
}
