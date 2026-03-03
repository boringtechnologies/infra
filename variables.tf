variable "region" {
  description = "AWS region to deploy resources in"
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  default     = "default"
}

variable "mongodb_uri" {
  type      = string
  sensitive = true
}

variable "account_alias" {
  type = string
}

variable "base_url" {
  type = string
}

variable "stripe_secret_key_dev" {
  description = "Stripe secret key for dev"
  type        = string
  sensitive   = true
}

variable "stripe_secret_key_prod" {
  description = "Stripe secret key for production"
  type        = string
  sensitive   = true
}

variable "webhook_signing_secret_dev" {
  description = "Stripe webhook secret for dev"
  type        = string
  sensitive   = true
}

variable "webhook_signing_secret_prod" {
  description = "Stripe webhook secret for production"
  type        = string
  sensitive   = true
}

variable "stripe_price_cents" {
  description = "Price in cents"
  type        = number
}

variable "stripe_product_id" {
  description = "Stripe product ID"
  type        = string
}

variable "dev_basic_auth_password" {
  description = "Password for basic auth on dev sites"
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "JWT signing secret for Falcon API authentication"
  type        = string
  sensitive   = true
}

variable "falcon_db_name" {
  description = "MongoDB database name for Falcon API"
  type        = string
  default     = "falconmdpa"
}