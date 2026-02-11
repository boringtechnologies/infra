# boring AWS Infrastructure

This repository contains the complete Terraform infrastructure as code (IaC) for boring's AWS environment, including static websites, API Gateway, Lambda functions, CloudFront distributions, and CI/CD pipelines.

---

## 🏗️ Architecture Overview

### Infrastructure Components

- **Static Websites** - Next.js/MkDocs sites on S3 + CloudFront
  - Production website (`boring.tech`)
  - Documentation (`docs.boring.tech`)

- **API Gateway** - RESTful API at `api.boring.tech`
  - 12 Lambda endpoints for user management, authentication, and webhooks
  - Custom domain with SSL/TLS (ACM certificate)

- **Lambda Functions** (Python 3.11)
  - User management (create, delete, login, password reset)
  - Cryptlex integration (licensing, activation management)
  - Stripe webhook processing
  - Email notifications
  - Usage analytics and logging

- **DynamoDB Tables**
  - Usage logs
  - Organization overview
  - Usage log streams

- **CI/CD Pipelines** - CodePipeline + CodeBuild
  - Automated deployments from GitHub
  - CloudFront cache invalidation
  - Separate dev and production environments

- **Security**
  - KMS encryption for Lambda secrets
  - CloudFront Origin Access Control (OAC) for S3
  - IAM roles with least-privilege access
  - SSL/TLS certificates via ACM

---

## 📋 Prerequisites

### Required Tools

- [Terraform](https://www.terraform.io/downloads) >= 1.6.0
- [AWS CLI](https://aws.amazon.com/cli/) v2
- [Docker](https://www.docker.com/) (for building Lambda layers)
- Bash shell

### AWS Credentials

Configure AWS CLI with your profile:

```bash
aws configure --profile boring-tech
```

### Secrets Configuration

Create `secrets.tfvars` in the repository root:

```hcl
# AWS Configuration
aws_profile = "boring-tech"
region      = "us-east-1"

# Cryptlex API
mongodb_uri = "your-mongodb-uri"
account_alias    = "your-account-alias"
base_url         = "https://api.cryptlex.com/v3"

# Stripe (Production)
stripe_secret_key_prod        = "sk_live_..."
webhook_signing_secret_prod   = "whsec_..."
stripe_price_cents            = 2999
stripe_product_id             = "prod_..."

# Stripe (dev)
stripe_secret_key_dev     = "sk_test_..."
webhook_signing_secret_dev = "whsec_..."
```

**⚠️ Never commit `secrets.tfvars` to version control!**

---

## 🚀 Deployment

### Step 1: Package Lambda Functions

Build all Lambda function ZIP files:

```bash
cd ./scripts
./zip_lambdas.sh
```

This creates `lambda.zip` files in each `modules/lambda/*/` directory.

### Step 2: Initialize Terraform

First-time setup or after adding new providers:

```bash
terraform init -upgrade
```

### Step 3: Preview Changes

Review what will be created/modified:

```bash
terraform plan -var-file="secrets.tfvars"
```

### Step 4: Deploy Infrastructure

Apply the Terraform configuration:

```bash
terraform apply -var-file="secrets.tfvars"
```

Lambda layers will be automatically built using Docker during this step.

### Step 5: Activate GitHub Connection

After first deployment, manually activate the CodeStar GitHub connection:

1. Go to AWS Console → Developer Tools → Connections
2. Find `boring-github` connection (status will be "Pending")
3. Click "Update pending connection"
4. Authorize GitHub access
5. Select the GitHub organization/account: `boringtechnologies` and/or `boring-dev`
6. Click "Connect"

**Important Notes:**
- The GitHub connection is used for CI/CD pipelines for **NextJS sites only** (boring-web, psych-web, bca-web, etc.)
- The **infra repository itself does not need a pipeline** - it's managed manually via Terraform
- After activation, the connection can access the following repositories:
  - `boringtechnologies/boring-web`
  - `boringtechnologies/psych-web`
  - `boringtechnologies/bca-web`
  - `boring-dev/portal`
  - `boring-dev/docs`

**Troubleshooting:**
- If the connection doesn't see your repositories, ensure you've authorized the correct GitHub organization
- The connection needs access to the organizations where the source repositories are located
- You may need to install the AWS Connector for GitHub app in your GitHub organization
- For the `infra` repository: it doesn't appear in the connection because it has no CodePipeline configured (infrastructure changes are deployed via `terraform apply`)

---

## 📁 Repository Structure

```
infra/
├── main.tf                      # Root configuration
├── variables.tf                 # Variable definitions
├── secrets.tfvars              # Secrets (gitignored)
├── scripts/
│   └── build-lambda-layer.sh   # Lambda layer builder
├── lambda-layers/
│   ├── stripe-layer/           # Stripe + requests
│   └── common-layer/           # Common dependencies
├── modules/
│   ├── api-gateway/            # API Gateway configuration
│   ├── iam/                    # IAM roles and policies
│   ├── lambda/                 # Individual Lambda functions
│   │   ├── list-records/
│   │   ├── update-records/
│   │   └── ...
│   ├── lambda-endpoint/        # Lambda + API Gateway integration
│   ├── nextjs-static-site/     # S3 + CloudFront for static sites
│   └── nextjs-pipeline/        # CodePipeline + CodeBuild
└── zip_lambdas.sh              # Package Lambda functions
```

---

## 🔧 Common Operations

### Update a Lambda Function

1. Edit code in `modules/lambda/<function-name>/`
2. Re-run packaging: `./zip_lambdas.sh`
3. Apply changes: `terraform apply -var-file="secrets.tfvars"`

### Add a New Lambda Function

1. Create directory: `modules/lambda/new-function/`
2. Add Python code (must have `lambda_handler` function)
3. Add to `local.lambda_configs` in `main.tf`:

```hcl
"new-function" = {
  environment = "common"
  layers      = ["common"]
}
```

4. Package and deploy: `./zip_lambdas.sh && terraform apply -var-file="secrets.tfvars"`

### Rebuild Lambda Layers

Lambda layers are automatically rebuilt when dependencies change. To force rebuild:

```bash
terraform taint null_resource.build_stripe_layer
terraform taint null_resource.build_common_layer
terraform apply -var-file="secrets.tfvars"
```

### Invalidate CloudFront Cache

```bash
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --paths "/*" \
  --profile boring-tech
```

Get distribution IDs from Terraform outputs:

```bash
terraform output nextjs_sites
```

### Deploy to Dev vs Production

Lambda environment variables are configured per function in `main.tf`:

```hcl
"stripe-webhook" = {
  environment = "production"  # or "dev"
  layers      = ["stripe", "common"]
}
```

---

## 🔐 Security Best Practices

- **Secrets Management** - Never commit `secrets.tfvars`
- **KMS Encryption** - All Lambda secrets encrypted at rest
- **S3 Security** - All buckets block public access (CloudFront uses OAC)
- **HTTPS Only** - CloudFront enforces HTTPS redirect
- **IAM Least Privilege** - Each Lambda has minimal required permissions
- **Key Rotation** - KMS key rotation enabled

---

## 📊 Outputs

After deployment, Terraform provides:

```bash
# API Gateway URL
terraform output api_custom_domain

# All Lambda endpoint URLs
terraform output lambda_endpoints

# All static site URLs and CloudFront IDs
terraform output nextjs_sites
```

---

## 🛠️ Manual Setup Required

The following resources must be created manually (not managed by Terraform):

1. **Domain Registration** - `boring.tech` registered via Route53 or external registrar
2. **GitHub Connection** - Initial CodeStar connection activation (one-time)
3. **IAM User** - `terraform-infra` user with appropriate permissions

---

## 🐛 Troubleshooting

### Lambda Layer Build Fails

**Error:** `entrypoint requires the handler name to be the first argument`

**Solution:** Ensure Docker is running and the build script has proper entrypoint override.

### CloudFront CNAME Already Exists

**Error:** `CNAMEAlreadyExists`

**Solution:** Remove the alias from the conflicting distribution:

```bash
aws cloudfront list-conflicting-aliases \
  --alias www.boring.tech \
  --distribution-id <YOUR_DIST_ID> \
  --profile boring-tech
```

### Terraform State Lock

**Error:** `Error acquiring the state lock`

**Solution:** If no other `terraform apply` is running:

```bash
terraform force-unlock <LOCK_ID>
```

---

## 📝 TODO

- [ ] Add Route53 DNS Records to Terraform
- [ ] Add Cost Tracking by Tag
