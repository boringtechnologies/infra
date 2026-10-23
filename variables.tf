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

variable "openai_api_key" {
  description = "OpenAI API key used to assess opportunity fit"
  type        = string
  sensitive   = true
}

variable "sam_api_key" {
  description = "SAM.gov public opportunities API key"
  type        = string
  sensitive   = true
}

variable "brave_search_api_key" {
  description = "Brave Search API key for public and private opportunity discovery"
  type        = string
  sensitive   = true
}

variable "opportunity_email_to" {
  description = "Email address receiving the opportunity digest"
  type        = string
}

variable "opportunity_email_from" {
  description = "Verified SES sender email address"
  type        = string
}

variable "opportunity_minimum_score" {
  description = "Minimum LLM match score included in the opportunity digest"
  type        = number
  default     = 70

  validation {
    condition     = var.opportunity_minimum_score >= 0 && var.opportunity_minimum_score <= 100
    error_message = "opportunity_minimum_score must be between 0 and 100."
  }
}

variable "opportunity_lookback_days" {
  description = "Number of recent days of opportunities to search (SAM.gov allows at most 365)"
  type        = number
  default     = 7

  validation {
    condition     = var.opportunity_lookback_days >= 1 && var.opportunity_lookback_days <= 365
    error_message = "opportunity_lookback_days must be between 1 and 365."
  }
}

variable "opportunity_schedule" {
  description = "EventBridge schedule expression for the opportunity digest Lambda"
  type        = string
  default     = "rate(1 day)"
}

variable "opportunity_openai_model" {
  description = "OpenAI model used for structured opportunity scoring"
  type        = string
  default     = "gpt-4o-mini"
}

variable "opportunity_max_ai_candidates_per_company" {
  description = "Maximum ranked opportunities per company sent to AI per daily run"
  type        = number
  default     = 20

  validation {
    condition     = var.opportunity_max_ai_candidates_per_company >= 1 && var.opportunity_max_ai_candidates_per_company <= 30
    error_message = "opportunity_max_ai_candidates_per_company must be between 1 and 30."
  }
}

variable "opportunity_include_possible_matches" {
  description = "Include pursuit-fit scores from 65 through 79 in a separate digest section"
  type        = bool
  default     = false
}