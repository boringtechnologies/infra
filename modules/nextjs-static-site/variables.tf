variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
}

variable "domain_name" {
  description = "Custom domain name (e.g., portal.boring.tech)"
  type        = string
  default     = null
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN (must be in us-east-1)"
  type        = string
  default     = null
}

variable "route53_zone_id" {
  description = "Route53 zone ID for DNS record"
  type        = string
  default     = null
}

variable "price_class" {
  description = "CloudFront price class"
  type        = string
  default     = "PriceClass_100"
}

variable "basic_auth_enabled" {
  description = "Enable basic authentication for this site"
  type        = bool
  default     = false
}

variable "basic_auth_username" {
  description = "Username for basic authentication"
  type        = string
  default     = ""
}

variable "basic_auth_password" {
  description = "Password for basic authentication"
  type        = string
  sensitive   = true
  default     = ""
}