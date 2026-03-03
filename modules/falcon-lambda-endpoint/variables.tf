variable "lambda_name" {
  type = string
}

variable "lambda_zip_path" {
  type = string
}

variable "handler" {
  type    = string
  default = "handler.lambda_handler"
}

variable "runtime" {
  type    = string
  default = "python3.13"
}

variable "role_arn" {
  type = string
}

variable "layers" {
  type    = list(string)
  default = []
}

variable "environment_variables" {
  type = map(string)
}

variable "rest_api_id" {
  type = string
}

variable "parent_resource_id" {
  type = string
}

variable "path_part" {
  type = string
}

variable "execution_arn" {
  type = string
}

variable "region" {
  type = string
}

variable "timeout" {
  type        = number
  default     = 900
  description = "Lambda function timeout in seconds (max 900 = 15 minutes)"
}
