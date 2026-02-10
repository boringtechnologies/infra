# Troubleshooting Guide

## Table of Contents
1. [Route53 Certificate Validation State Drift](#route53-certificate-validation-state-drift)
2. [API Gateway Service-Linked Role Permissions](#api-gateway-service-linked-role-permissions)

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

## API Gateway Service-Linked Role Permissions

### Problem

You may encounter this error when running `terraform apply`:

```
Error: creating API Gateway Domain Name (api.boring.tech): operation error API Gateway: CreateDomainName, https response error StatusCode: 403, RequestID: e8485ca4-c083-4328-9949-ad278a0cde2c, api error AccessDeniedException: Caller does not have permissions to create a Service Linked Role.

  with aws_api_gateway_domain_name.api,
  on main.tf line 169, in resource "aws_api_gateway_domain_name" "api":
 169: resource "aws_api_gateway_domain_name" "api" {
```

### Root Cause

API Gateway requires a service-linked role (`AWSServiceRoleForAPIGateway`) to function properly. When creating an API Gateway custom domain name for the first time in an AWS account, AWS attempts to automatically create this service-linked role. If the IAM user/role executing Terraform doesn't have the `iam:CreateServiceLinkedRole` permission, this operation fails.

### Solution

The infrastructure now includes an explicit `aws_iam_service_linked_role` resource that creates the service-linked role for API Gateway. This ensures:

1. The role is created with proper permissions through Terraform
2. The API Gateway domain depends on this role being created first
3. The creation is idempotent (won't fail if the role already exists)

The fix is already implemented in `main.tf`:

```hcl
resource "aws_iam_service_linked_role" "apigateway" {
  aws_service_name = "apigateway.amazonaws.com"
  description      = "Service-linked role for API Gateway"

  lifecycle {
    ignore_changes = [description]
  }
}
```

### Manual Alternative (If Needed)

If you prefer to create the service-linked role manually or if the automated creation still fails, you can create it using the AWS CLI:

```bash
aws iam create-service-linked-role --aws-service-name apigateway.amazonaws.com
```

After creating it manually, import it into Terraform state:

```bash
terraform import aws_iam_service_linked_role.apigateway arn:aws:iam::ACCOUNT_ID:role/aws-service-role/apigateway.amazonaws.com/AWSServiceRoleForAPIGateway
```

Replace `ACCOUNT_ID` with your AWS account ID.

### Prevention

The Terraform configuration now automatically manages this service-linked role, so this error should not occur in future deployments. The role will be created during the first `terraform apply` and persist across subsequent runs.

### Important Notes

- This service-linked role is required for all API Gateway custom domain names
- The role is created once per AWS account, not per region or resource
- The `ignore_changes` lifecycle policy prevents unnecessary updates
- If the role already exists in your account, Terraform will adopt it

### Reference

- AWS Service-Linked Roles: https://docs.aws.amazon.com/IAM/latest/UserGuide/using-service-linked-roles.html
- API Gateway Service-Linked Role: https://docs.aws.amazon.com/apigateway/latest/developerguide/using-service-linked-roles.html
