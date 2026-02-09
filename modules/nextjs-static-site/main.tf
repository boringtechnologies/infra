# CloudFront Function for request handling (auth + URI rewriting)
resource "aws_cloudfront_function" "request_handler" {
  name    = "${var.bucket_name}-request-handler"
  runtime = "cloudfront-js-2.0"
  comment = "Handle auth and URI rewriting for ${var.bucket_name}"
  publish = true
  code    = var.basic_auth_enabled ? (<<-EOT
function handler(event) {
    var request = event.request;
    var headers = request.headers;
    var uri = request.uri;
    
    // Basic authentication
    var authUser = '${var.basic_auth_username}';
    var authPass = '${var.basic_auth_password}';
    
    // Manually construct Basic Auth header value
    var expectedAuth = 'Basic ' + btoa(authUser + ':' + authPass);
    
    if (typeof headers.authorization === 'undefined' || headers.authorization.value !== expectedAuth) {
        return {
            statusCode: 401,
            statusDescription: 'Unauthorized',
            headers: {
                'www-authenticate': {
                    value: 'Basic realm="Restricted Area"'
                }
            }
        };
    }
    
    // Append index.html to directory requests
    if (uri.endsWith('/')) {
        request.uri += 'index.html';
    }
    else if (!uri.includes('.')) {
        request.uri += '/index.html';
    }
    
    return request;
}
EOT
  ) : (<<-EOT
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    
    // Append index.html to directory requests
    if (uri.endsWith('/')) {
        request.uri += 'index.html';
    }
    else if (!uri.includes('.')) {
        request.uri += '/index.html';
    }
    
    return request;
}
EOT
  )
}

# S3 Bucket for static site
resource "aws_s3_bucket" "site" {
  bucket = var.bucket_name

  tags = {
    Name      = var.bucket_name
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# Block public access to S3 bucket
resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudFront Origin Access Control
resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.bucket_name}-oac"
  description                       = "OAC for ${var.bucket_name}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = var.price_class
  
  # Add www for apex domain only
  aliases = var.domain_name != null ? concat(
    [var.domain_name],
    length(split(".", var.domain_name)) == 2 ? ["www.${var.domain_name}"] : []
  ) : []

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "S3-${var.bucket_name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${var.bucket_name}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true

    # Single function association for both auth and URI rewriting
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.request_handler.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.acm_certificate_arn == null ? true : false
    acm_certificate_arn            = var.acm_certificate_arn
    ssl_support_method             = var.acm_certificate_arn != null ? "sni-only" : null
    minimum_protocol_version       = var.acm_certificate_arn != null ? "TLSv1.2_2021" : null
  }

  tags = {
    Name      = "${var.bucket_name}-cdn"
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# S3 Bucket Policy
resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.site.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.site.arn
          }
        }
      }
    ]
  })
}

# Route53 A Record for main domain
resource "aws_route53_record" "site" {
  count   = var.domain_name != null && var.route53_zone_id != null ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

# Route53 A Record for www subdomain (only for apex domain)
resource "aws_route53_record" "site_www" {
  count   = var.domain_name != null && var.route53_zone_id != null && length(split(".", var.domain_name)) == 2 ? 1 : 0
  zone_id = var.route53_zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}