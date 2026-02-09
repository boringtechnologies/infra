# Fixing Route53 Certificate Validation State Drift

## Problem

You may encounter this error when running `terraform plan` or `terraform apply`:

```
Error: reading Route 53 Record (Z08845243VQND4TLD1KVI__31f76782931b2385bcfbf1fc1f8ea5ea.jouvencemedicalspa.com._CNAME): empty result

  with aws_route53_record.cert_validation_jouvencemedicalspa["_31f76782931b2385bcfbf1fc1f8ea5ea.jouvencemedicalspa.com."],
  on main.tf line 305, in resource "aws_route53_record" "cert_validation_jouvencemedicalspa":
 305: resource "aws_route53_record" "cert_validation_jouvencemedicalspa" {
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

## Reference

- AWS ACM Certificate Validation: https://docs.aws.amazon.com/acm/latest/userguide/dns-validation.html
- Terraform State Commands: https://www.terraform.io/cli/commands/state
