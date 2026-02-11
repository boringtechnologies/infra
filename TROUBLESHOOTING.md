# Troubleshooting Guide

## Table of Contents
1. [Lambda Layer Dependencies Not Updating](#lambda-layer-dependencies-not-updating)
2. [GitHub Connector Not Seeing Repository](#github-connector-not-seeing-repository)
3. [Route53 Certificate Validation State Drift](#route53-certificate-validation-state-drift)
4. [API Gateway Permissions Issues](#api-gateway-permissions-issues)

---

## Lambda Layer Dependencies Not Updating

### Problem

You added a new Python package to `lambda-layers/common-layer/requirements.txt` or `lambda-layers/stripe-layer/requirements.txt`, ran `terraform apply`, but Lambda functions still can't import the new package:

```
[ERROR] Runtime.ImportModuleError: Unable to import module 'handler': No module named 'pymongo'
```

### Root Cause

Lambda layers need to be rebuilt AND a new layer version must be created in AWS for the changes to take effect. Previously, the `aws_lambda_layer_version` resources were missing the `source_code_hash` attribute, which meant Terraform didn't detect when the layer zip file changed.

### Solution

**This issue has been fixed** as of commit c3b4694. The layer resources now include `source_code_hash` which automatically detects changes to the layer zip files.

#### For New Changes (After the Fix)

Simply run `terraform apply` after updating requirements.txt:

```bash
terraform apply -var-file="secrets.tfvars"
```

Terraform will:
1. Detect the change in requirements.txt (via filemd5 trigger)
2. Rebuild the layer zip file using Docker
3. Detect the change in the zip file (via source_code_hash)
4. Create a new layer version in AWS
5. Update Lambda functions to use the new layer version

#### If You Still Have Issues

1. **Verify Docker is running**:
   ```bash
   docker ps
   ```
   The layer build script requires Docker to create a Lambda-compatible environment.

2. **Check for layer build errors**:
   ```bash
   # Manually build the layer to see detailed output
   ./scripts/build-lambda-layer.sh common-layer lambda-layers/common-layer/requirements.txt
   ```

3. **Verify the package is in requirements.txt**:
   ```bash
   cat lambda-layers/common-layer/requirements.txt
   ```

4. **Check layer size** (AWS limit is 250MB uncompressed):
   ```bash
   ls -lh lambda-layers/common-layer.zip
   unzip -l lambda-layers/common-layer.zip | tail -1
   ```

5. **Verify Lambda runtime matches layer**:
   - Lambda functions use `python3.13` (default in `modules/lambda-endpoint/variables.tf`)
   - Lambda layers are built for `python3.13` (in Docker image)
   - Both must match for imports to work

### Prevention

- Always run `terraform apply` after updating requirements.txt
- The layer will automatically rebuild and redeploy
- No manual intervention needed (Docker handles the build)

### Reference

- AWS Lambda Layers: https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html
- Lambda Layer Limits: https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html

---

## GitHub Connector Not Seeing Repository

### Problem

You may see that the AWS CodeStar GitHub connection is not showing the `infra` repository or other expected repositories in AWS Developer Tools → Connections.

### Root Cause

There are several reasons why a repository might not appear:

1. **The infra repository doesn't need a pipeline** - This infrastructure repository is deployed manually via `terraform apply`, not through AWS CodePipeline
2. **Connection not activated** - The CodeStar connection must be manually activated after first Terraform deployment
3. **Wrong GitHub organization** - The connection needs access to the correct GitHub organizations
4. **AWS Connector app not installed** - GitHub organizations need the AWS Connector app installed

### Solution

#### For the Infra Repository

The `boringtechnologies/infra` repository **intentionally does not appear** in the CodeStar connection because:
- It has no CodePipeline configured
- Infrastructure changes are deployed manually using `terraform apply`
- Only NextJS application repositories need CI/CD pipelines

#### For NextJS Site Repositories

If your application repositories (boring-web, psych-web, etc.) don't appear:

1. **Activate the Connection** (first time only):
   ```bash
   # After terraform apply, go to AWS Console
   # Developer Tools → Connections → boring-github
   # Click "Update pending connection"
   # Authorize with GitHub
   ```

2. **Verify GitHub Organizations**:
   - Ensure you authorize both `boringtechnologies` and `boring-dev` organizations
   - Check that you have admin access to these organizations

3. **Install AWS Connector App**:
   - Go to GitHub → Organization Settings → Installed GitHub Apps
   - Install "AWS Connector for GitHub" if not present
   - Grant access to required repositories

4. **Check Repository Access**:
   ```bash
   # List which repositories the connection can see
   aws codestar-connections list-repositories \
     --connection-arn arn:aws:codestar-connections:REGION:ACCOUNT:connection/CONNECTION_ID
   ```

#### Configured Repositories

The following repositories are configured in the infrastructure:

- `boringtechnologies/boring-web` → deployed to boring.tech
- `boringtechnologies/psych-web` → deployed to boringpsych.com
- `boringtechnologies/bca-web` → deployed to boringmd.org
- `boring-dev/portal` → deployed to jouvencemedicalspa.com
- `boring-dev/docs` → deployed to docs.boring.tech
- `boringtechnologies/infra` → **NO PIPELINE** (manual deployment only)

### Prevention

- The infra repository will never need a CodeStar connection
- For new application repositories, add them to `local.nextjs_sites` in `main.tf`
- Always activate the CodeStar connection after first deployment
- Ensure proper GitHub organization permissions before deploying

### Reference

- AWS CodeStar Connections: https://docs.aws.amazon.com/dtconsole/latest/userguide/connections.html
- GitHub App Installation: https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app

---

## Route53 Certificate Validation State Drift

### Problem

You may encounter this error when running `terraform plan` or `terraform apply`:

```
Error: reading Route 53 Record (Z08845243VQND4TLD1KVI__31f76782931b2385bcfbf1fc1f8ea5ea.jouvencemedicalspa.com._CNAME): empty result

  with aws_route53_record.cert_validation_jouvencemedicalspa["_31f76782931b2385bcfbf1fc1f8ea5ea.jouvencemedicalspa.com."],
  on main.tf line 313, in resource "aws_route53_record" "cert_validation_jouvencemedicalspa":
 313: resource "aws_route53_record" "cert_validation_jouvencemedicalspa" {
```

## Root Cause

This error occurs when:
1. Terraform state contains a reference to a Route53 record that no longer exists in AWS
2. The record may have been manually deleted or cleaned up by AWS after certificate validation
3. There's a mismatch between Terraform state and actual AWS resources

## Solution Options

### Option 1: Remove from State (Recommended for Quick Fix)

Remove the orphaned resource from Terraform state:

```bash
# Remove specific resource
terraform state rm 'aws_route53_record.cert_validation_jouvencemedicalspa["_31f76782931b2385bcfbf1fc1f8ea5ea.jouvencemedicalspa.com."]'

# Then re-run terraform plan/apply
terraform plan
terraform apply
```

Alternatively, use the provided script:

```bash
# Make the script executable if needed
chmod +x fix-state-drift.sh

# Run the script
./fix-state-drift.sh
```

### Option 2: Refresh State

Sometimes a simple state refresh can help:

```bash
terraform refresh -var-file="secrets.tfvars"
```

### Option 3: Target Specific Resources

If you need to recreate specific certificate validation:

```bash
# Target the certificate resource
terraform apply -target=aws_acm_certificate.domain_certs["jouvencemedicalspa.com"] -var-file="secrets.tfvars"

# Then apply the validation records
terraform apply -target=aws_route53_record.cert_validation_jouvencemedicalspa -var-file="secrets.tfvars"
```

## Prevention

The configuration now includes `lifecycle { create_before_destroy = true }` blocks on all certificate validation resources to help prevent similar issues in the future. This ensures that new validation records are created before old ones are destroyed during updates.

## Important Notes

- Certificate validation records are typically only needed during initial certificate creation
- Once a certificate is validated, these records can sometimes be safely removed
- ACM certificates automatically renew, so these records should ideally be kept in place
- The `allow_overwrite = true` setting allows Terraform to replace records if needed

## Troubleshooting

If the problem persists:

1. Check AWS Console to verify which Route53 records actually exist
2. Check ACM Console to verify certificate validation status
3. Consider recreating the entire certificate if validation is stuck
4. Review recent changes to the Terraform configuration or manual AWS changes

### Reference

- AWS ACM Certificate Validation: https://docs.aws.amazon.com/acm/latest/userguide/dns-validation.html
- Terraform State Commands: https://www.terraform.io/cli/commands/state

---

## API Gateway Permissions Issues

### Problem

You may encounter one of these errors when running `terraform apply`:

**Error 1: AccessDeniedException for Service Linked Role**
```
Error: creating API Gateway Domain Name (api.boring.tech): operation error API Gateway: CreateDomainName, https response error StatusCode: 403, RequestID: e8485ca4-c083-4328-9949-ad278a0cde2c, api error AccessDeniedException: Caller does not have permissions to create a Service Linked Role.
```

**Error 2: Cannot find Service Linked Role template**
```
Error: creating IAM Service Linked Role (apigateway.amazonaws.com): operation error IAM: CreateServiceLinkedRole, https response error StatusCode: 403, RequestID: 0cca8df9-3abb-4019-8a05-a4d1ad36720a, api error AccessDenied: Cannot find Service Linked Role template for apigateway.amazonaws.com
```

### Root Cause

API Gateway does **not** require an explicitly created service-linked role like some other AWS services. The confusion arises because:

1. **Error 1** occurs when the IAM user/role lacks sufficient permissions to create API Gateway resources
2. **Error 2** occurs when trying to create a service-linked role that doesn't exist as a template for API Gateway
3. API Gateway creates any needed roles automatically when you have the correct base permissions

### Solution

The infrastructure has been updated to **remove** the explicit service-linked role creation. API Gateway will handle role creation automatically when needed.

**Required IAM Permissions:**

Your Terraform execution role needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "apigateway:*",
        "acm:DescribeCertificate",
        "acm:ListCertificates"
      ],
      "Resource": "*"
    }
  ]
}
```

### Manual Workaround

If you're still experiencing permissions issues, ensure your IAM user/role has:

1. **AdministratorAccess** (for testing/development), or
2. **Specific permissions** for API Gateway operations:
   - `apigateway:POST`
   - `apigateway:GET`
   - `apigateway:PATCH`
   - `apigateway:DELETE`

You can test permissions with:

```bash
# Check if you can create API Gateway resources
aws apigateway get-rest-apis --region us-east-1

# Check your current IAM identity
aws sts get-caller-identity
```

### Prevention

- Ensure the Terraform execution role has adequate API Gateway permissions
- API Gateway doesn't require explicit service-linked role management
- Let AWS handle automatic role creation as needed

### Important Notes

- **No service-linked role needed**: API Gateway manages its own internal roles
- **Permissions matter**: Focus on granting proper `apigateway:*` permissions
- **Regional resources**: API Gateway domains are regional, ensure correct region configuration
- **Certificate prerequisites**: Ensure ACM certificates are validated before creating custom domains

### Reference

- AWS API Gateway Permissions: https://docs.aws.amazon.com/apigateway/latest/developerguide/permissions.html
