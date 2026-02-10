#!/bin/bash
# Script to fix Route53 certificate validation state drift
# This removes orphaned resources from Terraform state that no longer exist in AWS

set -e

echo "Fixing Route53 certificate validation state drift..."
echo ""
echo "This will remove orphaned Route53 validation records from Terraform state."
echo "Terraform will recreate them on the next apply if they're still needed."
echo ""

# List of potentially orphaned resources
RESOURCES=(
    'aws_route53_record.cert_validation_jouvencemedicalspa["_31f76782931b2385bcfbf1fc1f8ea5ea.jouvencemedicalspa.com."]'
)

for resource in "${RESOURCES[@]}"; do
    echo "Checking: $resource"
    if terraform state list | grep -q "$resource"; then
        echo "  Found in state. Removing..."
        terraform state rm "$resource" || echo "  Warning: Could not remove $resource"
    else
        echo "  Not found in state (already removed or never existed)"
    fi
done

echo ""
echo "Done! Now run 'terraform plan' to see what Terraform will recreate."
echo "Then run 'terraform apply' to fix the infrastructure."
