terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.6.0"
}

# Default provider (no alias) - used by modules
provider "aws" {
  region  = var.region
  profile = var.aws_profile
}

# US East 1 provider for CloudFront certificates
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile
}

data "aws_caller_identity" "current" {}

# KMS Key for Lambda encryption (created first, policy added later)
resource "aws_kms_key" "lambda_encryption" {
  description             = "KMS key for boring Lambda encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = {
    Name      = "boring Lambda Encryption Key"
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# KMS Key Alias
resource "aws_kms_alias" "lambda_encryption" {
  name          = "alias/boring-cookie-kms-key"
  target_key_id = aws_kms_key.lambda_encryption.key_id
}

# Add this - lookup your existing Route53 hosted zones
data "aws_route53_zone" "boring" {
  name         = "boring.tech"
  private_zone = false
}

data "aws_route53_zone" "boringpsych" {
  name         = "boringpsych.com"
  private_zone = false
}

data "aws_route53_zone" "jouvencemedicalspa" {
  name         = "jouvencemedicalspa.com"
  private_zone = false
}

data "aws_route53_zone" "boringmd" {
  name         = "boringmd.org"
  private_zone = false
}

data "aws_route53_zone" "falconmdpa" {
  name         = "falconmdpa.com"
  private_zone = false
}

# Shared API Gateway
module "api_gateway" {
  source = "./modules/api-gateway"
}

# IAM roles for Lambda functions
module "iam" {
  source      = "./modules/iam"
  kms_key_arn = aws_kms_key.lambda_encryption.arn
}

locals {
  # Define lambda configurations with env and layers
  lambda_configs = {
    "list-records" = {
      environment = "common"
      layers      = ["common"]
    }
    "list-users" = {
      environment = "common"
      layers      = ["common"]
    }
    "update-records" = {
      environment = "common"
      layers      = ["common"]
    }
  }

  # Map layer names to ARNs
  layer_arns = {
    "stripe" = aws_lambda_layer_version.stripe.arn
    "common" = aws_lambda_layer_version.common.arn
  }

  # Environment variable sets
  env_vars_common = {
    ACCOUNT_ALIAS = var.account_alias
    MONGODB_URI   = var.mongodb_uri
    BASE_URL      = var.base_url
  }

  env_vars_dev = merge(local.env_vars_common, {
    STRIPE_SECRET_KEY      = var.stripe_secret_key_dev
    WEBHOOK_SIGNING_SECRET = var.webhook_signing_secret_dev
    PRICE_CENTS            = tostring(var.stripe_price_cents)
    PRODUCT_ID             = var.stripe_product_id
  })

  env_vars_production = merge(local.env_vars_common, {
    STRIPE_SECRET_KEY      = var.stripe_secret_key_prod
    WEBHOOK_SIGNING_SECRET = var.webhook_signing_secret_prod
    PRICE_CENTS            = tostring(var.stripe_price_cents)
    PRODUCT_ID             = var.stripe_product_id
  })
}

module "lambdas" {
  source   = "./modules/lambda-endpoint"
  for_each = local.lambda_configs # This loops through all lambda names

  lambda_name     = "boring-${each.key}"
  lambda_zip_path = "./modules/lambda/${each.key}/lambda.zip"
  role_arn        = module.iam.lambda_exec_role_arn
  region          = var.region
  path_part       = each.key

  rest_api_id        = module.api_gateway.rest_api_id
  parent_resource_id = module.api_gateway.root_resource_id
  execution_arn      = module.api_gateway.execution_arn

  # Use configured layers
  layers = [
    for layer_name in each.value.layers : local.layer_arns[layer_name]
  ]

  # Use environment-specific variables
  environment_variables = (
    each.value.environment == "dev" ? local.env_vars_dev :
    each.value.environment == "production" ? local.env_vars_production :
    local.env_vars_common
  )
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "boring_api_deploy" {
  depends_on = [module.lambdas]

  rest_api_id = module.api_gateway.rest_api_id

  lifecycle {
    create_before_destroy = true
  }
}

# API Gateway Stage
resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = module.api_gateway.rest_api_id
  stage_name    = "prod"
  deployment_id = aws_api_gateway_deployment.boring_api_deploy.id
}

# API Gateway Custom Domain
resource "aws_api_gateway_domain_name" "api" {
  domain_name              = "api.boring.tech"
  regional_certificate_arn = aws_acm_certificate_validation.domain_certs["boring.tech"].certificate_arn

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name      = "boring API Domain"
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# Base Path Mapping - maps the domain to your API Gateway stage
resource "aws_api_gateway_base_path_mapping" "api" {
  api_id      = module.api_gateway.rest_api_id
  stage_name  = aws_api_gateway_stage.prod.stage_name
  domain_name = aws_api_gateway_domain_name.api.domain_name
}

# Route53 A Record for api.boring.tech
resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.boring.zone_id
  name    = "api.boring.tech"
  type    = "A"

  alias {
    name                   = aws_api_gateway_domain_name.api.regional_domain_name
    zone_id                = aws_api_gateway_domain_name.api.regional_zone_id
    evaluate_target_health = false
  }
}

# Output the custom domain URL
output "api_custom_domain" {
  value = "https://${aws_api_gateway_domain_name.api.domain_name}"
}

# This automatically creates outputs for ALL lambdas
output "lambda_endpoints" {
  value = {
    for name in keys(local.lambda_configs) :
    name => "https://${module.api_gateway.api_id}.execute-api.${var.region}.amazonaws.com/${aws_api_gateway_stage.prod.stage_name}/${name}"
  }
}


# Certificates for all domains
locals {
  # Map of domain certificates
  domain_certificates = {
    "boring.tech" = {
      zone_id                   = data.aws_route53_zone.boring.zone_id
      domain_name               = "*.boring.tech"
      subject_alternative_names = ["boring.tech"]
    }
    "boringpsych.com" = {
      zone_id                   = data.aws_route53_zone.boringpsych.zone_id
      domain_name               = "*.boringpsych.com"
      subject_alternative_names = ["boringpsych.com"]
    }
    "jouvencemedicalspa.com" = {
      zone_id                   = data.aws_route53_zone.jouvencemedicalspa.zone_id
      domain_name               = "*.jouvencemedicalspa.com"
      subject_alternative_names = ["jouvencemedicalspa.com"]
    }
    "boringmd.org" = {
      zone_id                   = data.aws_route53_zone.boringmd.zone_id
      domain_name               = "*.boringmd.org"
      subject_alternative_names = ["boringmd.org"]
    }
    "falconmdpa.com" = {
      zone_id                   = data.aws_route53_zone.falconmdpa.zone_id
      domain_name               = "*.falconmdpa.com"
      subject_alternative_names = ["falconmdpa.com"]
    }
  }
}

# Create ACM certificates for all domains
resource "aws_acm_certificate" "domain_certs" {
  for_each = local.domain_certificates
  provider = aws.us_east_1

  domain_name               = each.value.domain_name
  subject_alternative_names = each.value.subject_alternative_names
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name      = "${each.key} Wildcard Certificate"
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# DNS validation for all certificates - separate resources per domain to avoid dynamic for_each keys
resource "aws_route53_record" "cert_validation_boring_tech" {
  for_each = { validation = true }

  allow_overwrite = true
  name = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boring.tech"].domain_validation_options : dvo.resource_record_name
  ]))
  records = [one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boring.tech"].domain_validation_options : dvo.resource_record_value
  ]))]
  ttl = 60
  type = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boring.tech"].domain_validation_options : dvo.resource_record_type
  ]))
  zone_id = local.domain_certificates["boring.tech"].zone_id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation_boringpsych" {
  for_each = { validation = true }

  allow_overwrite = true
  name = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boringpsych.com"].domain_validation_options : dvo.resource_record_name
  ]))
  records = [one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boringpsych.com"].domain_validation_options : dvo.resource_record_value
  ]))]
  ttl = 60
  type = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boringpsych.com"].domain_validation_options : dvo.resource_record_type
  ]))
  zone_id = local.domain_certificates["boringpsych.com"].zone_id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation_jouvencemedicalspa" {
  for_each = { validation = true }

  allow_overwrite = true
  name = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["jouvencemedicalspa.com"].domain_validation_options : dvo.resource_record_name
  ]))
  records = [one(distinct([
    for dvo in aws_acm_certificate.domain_certs["jouvencemedicalspa.com"].domain_validation_options : dvo.resource_record_value
  ]))]
  ttl = 60
  type = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["jouvencemedicalspa.com"].domain_validation_options : dvo.resource_record_type
  ]))
  zone_id = local.domain_certificates["jouvencemedicalspa.com"].zone_id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation_boringmd" {
  for_each = { validation = true }

  allow_overwrite = true
  name = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boringmd.org"].domain_validation_options : dvo.resource_record_name
  ]))
  records = [one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boringmd.org"].domain_validation_options : dvo.resource_record_value
  ]))]
  ttl = 60
  type = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["boringmd.org"].domain_validation_options : dvo.resource_record_type
  ]))
  zone_id = local.domain_certificates["boringmd.org"].zone_id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation_falconmdpa" {
  for_each = { validation = true }

  allow_overwrite = true
  name = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["falconmdpa.com"].domain_validation_options : dvo.resource_record_name
  ]))
  records = [one(distinct([
    for dvo in aws_acm_certificate.domain_certs["falconmdpa.com"].domain_validation_options : dvo.resource_record_value
  ]))]
  ttl = 60
  type = one(distinct([
    for dvo in aws_acm_certificate.domain_certs["falconmdpa.com"].domain_validation_options : dvo.resource_record_type
  ]))
  zone_id = local.domain_certificates["falconmdpa.com"].zone_id

  lifecycle {
    create_before_destroy = true
  }
}

moved {
  from = aws_route53_record.cert_validation_boring_tech["_a654b5e72bd8e69d9a2f782f7fb51848.boring.tech."]
  to   = aws_route53_record.cert_validation_boring_tech["validation"]
}

moved {
  from = aws_route53_record.cert_validation_boringpsych["_25601956cada26796e4ef9f2b5879be9.boringpsych.com."]
  to   = aws_route53_record.cert_validation_boringpsych["validation"]
}

moved {
  from = aws_route53_record.cert_validation_jouvencemedicalspa["_31f76782931b2385bcfbf1fc1f8ea5ea.jouvencemedicalspa.com."]
  to   = aws_route53_record.cert_validation_jouvencemedicalspa["validation"]
}

moved {
  from = aws_route53_record.cert_validation_boringmd["_0fdad0364e19b20e0aa765212c6a2a9c.boringmd.org."]
  to   = aws_route53_record.cert_validation_boringmd["validation"]
}

moved {
  from = aws_route53_record.cert_validation_falconmdpa["_ed578b761f90aadb4c65b670543eb43f.falconmdpa.com."]
  to   = aws_route53_record.cert_validation_falconmdpa["validation"]
}

resource "aws_acm_certificate_validation" "domain_certs" {
  for_each = local.domain_certificates
  provider = aws.us_east_1

  certificate_arn = aws_acm_certificate.domain_certs[each.key].arn
  validation_record_fqdns = concat(
    each.key == "boring.tech" ? [for record in aws_route53_record.cert_validation_boring_tech : record.fqdn] : [],
    each.key == "boringpsych.com" ? [for record in aws_route53_record.cert_validation_boringpsych : record.fqdn] : [],
    each.key == "jouvencemedicalspa.com" ? [for record in aws_route53_record.cert_validation_jouvencemedicalspa : record.fqdn] : [],
    each.key == "boringmd.org" ? [for record in aws_route53_record.cert_validation_boringmd : record.fqdn] : [],
    each.key == "falconmdpa.com" ? [for record in aws_route53_record.cert_validation_falconmdpa : record.fqdn] : []
  )
}

# Define all your NextJS sites with pipeline config
locals {
  nextjs_sites = {
    myworkoutapp-web = {
      domain_name   = "myworkoutapp.boring.tech"
      github_repo   = "boringtechnologies/myworkoutapp-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
    wow-web = {
      domain_name   = "wowchicago.boring.tech"
      github_repo   = "boringtechnologies/wow-web"
      github_branch = "dev"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
    boring-web = {
      domain_name   = "boring.tech"
      github_repo   = "boringtechnologies/boring-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
    psych-web = {
      domain_name   = "boringpsych.com"
      github_repo   = "boringtechnologies/psych-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
    bca-web = {
      domain_name   = "boringmd.org"
      github_repo   = "boringtechnologies/bca-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
    medspa-web = {
      domain_name   = "jouvencemedicalspa.com"
      github_repo   = "boringtechnologies/medspa-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
    dev-medspa-web = {
      domain_name   = "dev.jouvencemedicalspa.com"
      github_repo   = "boringtechnologies/medspa-web"
      github_branch = "dev"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
    falcon-web = {
      domain_name   = "falconmdpa.com"
      github_repo   = "boringtechnologies/falcon-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
    records = {
      domain_name   = "records.boring.tech"
      github_repo   = "boringtechnologies/records-web"
      github_branch = "dev"
      enable_cicd   = true
      basic_auth = {
        enabled = false
      }
    }
  }

  # Helper function to extract base domain from full domain
  # Uses a whitelist approach based on known hosted zones
  domain_to_base = {
    for key, site in local.nextjs_sites :
    key => (
      # Check against known base domains in order
      can(regex("boring\\.tech$", site.domain_name)) ? "boring.tech" :
      can(regex("boringpsych\\.com$", site.domain_name)) ? "boringpsych.com" :
      can(regex("jouvencemedicalspa\\.com$", site.domain_name)) ? "jouvencemedicalspa.com" :
      can(regex("boringmd\\.org$", site.domain_name)) ? "boringmd.org" :
      can(regex("falconmdpa\\.com$", site.domain_name)) ? "falconmdpa.com" :
      # If no match, assume it's already a base domain
      site.domain_name
    )
  }

  # Lookup map for hosted zones
  zone_map = {
    "boring.tech"            = data.aws_route53_zone.boring.zone_id
    "boringpsych.com"        = data.aws_route53_zone.boringpsych.zone_id
    "jouvencemedicalspa.com" = data.aws_route53_zone.jouvencemedicalspa.zone_id
    "boringmd.org"           = data.aws_route53_zone.boringmd.zone_id
    "falconmdpa.com"         = data.aws_route53_zone.falconmdpa.zone_id
  }

  # Lookup map for certificates
  cert_map = {
    "boring.tech"            = aws_acm_certificate_validation.domain_certs["boring.tech"].certificate_arn
    "boringpsych.com"        = aws_acm_certificate_validation.domain_certs["boringpsych.com"].certificate_arn
    "jouvencemedicalspa.com" = aws_acm_certificate_validation.domain_certs["jouvencemedicalspa.com"].certificate_arn
    "boringmd.org"           = aws_acm_certificate_validation.domain_certs["boringmd.org"].certificate_arn
    "falconmdpa.com"         = aws_acm_certificate_validation.domain_certs["falconmdpa.com"].certificate_arn
  }

  # Map each site to its hosted zone
  site_to_zone = {
    for key, site in local.nextjs_sites :
    key => lookup(local.zone_map, local.domain_to_base[key], data.aws_route53_zone.boring.zone_id)
  }

  # Map each site to its certificate
  site_to_cert = {
    for key, site in local.nextjs_sites :
    key => lookup(local.cert_map, local.domain_to_base[key], aws_acm_certificate_validation.domain_certs["boring.tech"].certificate_arn)
  }
}

# Create all NextJS sites
module "nextjs_sites" {
  source   = "./modules/nextjs-static-site"
  for_each = local.nextjs_sites

  bucket_name         = "boring-${each.key}"
  domain_name         = each.value.domain_name
  acm_certificate_arn = local.site_to_cert[each.key]
  route53_zone_id     = local.site_to_zone[each.key]
  price_class         = "PriceClass_100"

  # Add basic auth configuration
  basic_auth_enabled  = each.value.basic_auth.enabled
  basic_auth_username = try(each.value.basic_auth.username, "")
  basic_auth_password = try(each.value.basic_auth.password, "")
}

# Output all site URLs
output "nextjs_sites" {
  value = {
    for key, site in module.nextjs_sites :
    key => {
      url               = site.website_url
      bucket_name       = site.bucket_name
      cloudfront_id     = site.cloudfront_id
      cloudfront_domain = site.cloudfront_domain_name
    }
  }
}

# CodeStar connection to GitHub (one-time setup)
# This connection is used for CI/CD pipelines for NextJS application repositories.
# It does NOT include the 'infra' repository itself (which is deployed manually via terraform).
# 
# After first deployment:
# 1. Go to AWS Console → Developer Tools → Connections
# 2. Find "boring-github" connection (status: Pending)
# 3. Click "Update pending connection"
# 4. Authorize GitHub access for organizations: boringtechnologies, boring-dev
# 5. Install AWS Connector app in GitHub organizations if needed
#
# Configured repositories (for CI/CD):
# - boringtechnologies/boring-web
# - boringtechnologies/psych-web
# - boringtechnologies/bca-web
# - boring-dev/portal
# - boring-dev/docs
resource "aws_codestarconnections_connection" "github" {
  name          = "boring-github"
  provider_type = "GitHub"
}

# S3 bucket for pipeline artifacts
resource "aws_s3_bucket" "pipeline_artifacts" {
  bucket = "boring-pipeline-artifacts"
}

resource "aws_s3_bucket_public_access_block" "pipeline_artifacts" {
  bucket = aws_s3_bucket.pipeline_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Create pipelines for all NextJS sites
module "nextjs_pipelines" {
  source   = "./modules/nextjs-pipeline"
  for_each = { for k, v in local.nextjs_sites : k => v if v.enable_cicd }

  project_name            = "boring-${each.key}"
  github_repo             = each.value.github_repo
  github_branch           = each.value.github_branch
  s3_bucket               = module.nextjs_sites[each.key].bucket_name
  codestar_connection_arn = aws_codestarconnections_connection.github.arn
  artifact_bucket         = aws_s3_bucket.pipeline_artifacts.bucket

  environment_variables = {
    S3_BUCKET          = module.nextjs_sites[each.key].bucket_name
    CLOUDFRONT_DIST_ID = module.nextjs_sites[each.key].cloudfront_id
    DEPLOY_ENV         = each.key == "dev-website" ? "dev" : "production"
  }
}

# Build Lambda layers using local-exec
resource "null_resource" "build_stripe_layer" {
  triggers = {
    requirements = filemd5("${path.module}/lambda-layers/stripe-layer/requirements.txt")
    build_script = filesha256("${path.module}/scripts/build-lambda-layer.sh")
  }

  provisioner "local-exec" {
    command = "${path.module}/scripts/build-lambda-layer.sh stripe-layer lambda-layers/stripe-layer/requirements.txt"
  }
}

# Stripe Lambda Layer
resource "aws_lambda_layer_version" "stripe" {
  depends_on = [null_resource.build_stripe_layer]

  filename         = "${path.module}/lambda-layers/stripe-layer.zip"
  layer_name       = "boring-stripe-layer"
  source_code_hash = base64sha256(null_resource.build_stripe_layer.id)

  compatible_runtimes = ["python3.13"]
}

# Common Python Layer (requests, etc.)
resource "null_resource" "build_common_layer" {
  triggers = {
    requirements = filemd5("${path.module}/lambda-layers/common-layer/requirements.txt")
    build_script = filesha256("${path.module}/scripts/build-lambda-layer.sh")
  }

  provisioner "local-exec" {
    command = "${path.module}/scripts/build-lambda-layer.sh common-layer lambda-layers/common-layer/requirements.txt"
  }
}

resource "aws_lambda_layer_version" "common" {
  depends_on = [null_resource.build_common_layer]

  filename         = "${path.module}/lambda-layers/common-layer.zip"
  layer_name       = "boring-common-layer"
  source_code_hash = base64sha256(null_resource.build_common_layer.id)

  compatible_runtimes = ["python3.13"]
}

# KMS Key Policy (allow Lambda to use it) - added after IAM module to avoid circular dependency
resource "aws_kms_key_policy" "lambda_encryption" {
  key_id = aws_kms_key.lambda_encryption.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow Lambda to use the key"
        Effect = "Allow"
        Principal = {
          AWS = module.iam.lambda_exec_role_arn
        }
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "opportunity_digest" {
  name = "boring-opportunity-digest-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Effect = "Allow"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "opportunity_digest_logs" {
  role       = aws_iam_role.opportunity_digest.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "opportunity_digest" {
  name = "boring-opportunity-digest-access"
  role = aws_iam_role.opportunity_digest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ses:SendEmail"]
      Resource = "arn:aws:ses:${var.region}:${data.aws_caller_identity.current.account_id}:identity/${try(split("@", var.opportunity_email_from)[1], var.opportunity_email_from)}"
    }]
  })
}

resource "aws_lambda_function" "opportunity_digest" {
  function_name    = "boring-opportunity-digest"
  filename         = "${path.module}/modules/lambda/opportunity-digest/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/modules/lambda/opportunity-digest/lambda.zip")
  handler          = "handler.lambda_handler"
  runtime          = "python3.13"
  role             = aws_iam_role.opportunity_digest.arn
  layers           = [aws_lambda_layer_version.common.arn]
  timeout          = 900
  memory_size      = 512

  environment {
    variables = {
      OPENAI_API_KEY                = var.openai_api_key
      OPENAI_MODEL                  = var.opportunity_openai_model
      MONGODB_URI                   = var.mongodb_uri
      SAM_API_KEY                   = var.sam_api_key
      BRAVE_SEARCH_API_KEY          = var.brave_search_api_key
      OPPORTUNITY_EMAIL_TO          = var.opportunity_email_to
      OPPORTUNITY_EMAIL_FROM        = var.opportunity_email_from
      MINIMUM_MATCH_SCORE           = tostring(var.opportunity_minimum_score)
      LOOKBACK_DAYS                 = tostring(var.opportunity_lookback_days)
      MAX_AI_CANDIDATES_PER_COMPANY = tostring(var.opportunity_max_ai_candidates_per_company)
      INCLUDE_POSSIBLE_MATCHES      = tostring(var.opportunity_include_possible_matches)
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.opportunity_digest_logs,
    aws_iam_role_policy.opportunity_digest,
  ]

  tags = {
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

resource "aws_cloudwatch_event_rule" "opportunity_digest" {
  name                = "boring-opportunity-digest-daily"
  description         = "Run the business opportunity digest on a configurable schedule"
  schedule_expression = var.opportunity_schedule
}

resource "aws_cloudwatch_event_target" "opportunity_digest" {
  rule      = aws_cloudwatch_event_rule.opportunity_digest.name
  target_id = "boring-opportunity-digest"
  arn       = aws_lambda_function.opportunity_digest.arn
}

resource "aws_lambda_permission" "opportunity_digest_events" {
  statement_id  = "AllowEventBridgeInvokeOpportunityDigest"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.opportunity_digest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.opportunity_digest.arn
}