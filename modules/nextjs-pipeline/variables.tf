variable "project_name" {
  description = "Name of the project (e.g., boring-dashboard)"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository in format 'owner/repo'"
  type        = string
}

variable "github_branch" {
  description = "GitHub branch to track"
  type        = string
  default     = "main"
}

variable "s3_bucket" {
  description = "S3 bucket name for the website"
  type        = string
}

variable "codestar_connection_arn" {
  description = "ARN of CodeStar connection to GitHub"
  type        = string
}

variable "artifact_bucket" {
  description = "S3 bucket for pipeline artifacts"
  type        = string
}

variable "environment_variables" {
  description = "Environment variables for CodeBuild"
  type        = map(string)
  default     = {}
}

variable "buildspec_path" {
  description = "Path to buildspec file in repo"
  type        = string
  default     = "buildspec.yml"
}