terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

########################################
# Providers
########################################
provider "aws" {
  profile = var.aws_profile
  region  = var.region
}

########################################
# Locals (single block)
########################################
locals {
  project_tag = "n8n-ec2"

  # https if a domain is set, else http
  protocol   = var.domain != "" ? "https" : "http"
  # value used in Caddyfile host line
  caddy_site = var.domain != "" ? var.domain : ":80"

  # Two env lines only when a domain is set, with correct YAML indentation
  webhook_env = var.domain != "" ? join("\n          ", [
    "WEBHOOK_URL: \"https://${var.domain}/\"",
    "N8N_PROXY_HOPS: \"1\"",
  ]) : ""
}

# Generate a key if one wasn't provided
resource "random_id" "enc" {
  byte_length = 32
}

locals {
  # Use coalesce with nonsensitive to handle the conditional without marking issues
  enc_key = coalesce(nonsensitive(var.n8n_encryption_key), random_id.enc.hex)
}

########################################
# Default VPC + one subnet
########################################
data "aws_vpc" "default" { default = true }

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

########################################
# Security Group (80/443 in; all egress)
########################################
resource "aws_security_group" "n8n" {
  name        = "${local.project_tag}-sg"
  description = "Allow HTTP/HTTPS"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Project = local.project_tag }
}

########################################
# IAM for EC2 + SSM
########################################
data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_role" {
  name               = "${local.project_tag}-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
  tags               = { Project = local.project_tag }
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Allow reading the SecureString key
resource "aws_iam_role_policy" "ssm_get_param" {
  name = "allow-n8n-ssm-get-parameter"
  role = aws_iam_role.ec2_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Sid      = "AllowGetParameter",
      Effect   = "Allow",
      Action   = ["ssm:GetParameter", "ssm:GetParameters"],
      Resource = aws_ssm_parameter.n8n_encryption_key.arn
    }]
  })
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${local.project_tag}-profile"
  role = aws_iam_role.ec2_role.name
}

########################################
# SSM Parameter for the encryption key
########################################
resource "aws_ssm_parameter" "n8n_encryption_key" {
  name  = "/n8n/encryption_key"
  type  = "SecureString"
  value = local.enc_key
  tags  = { Project = local.project_tag }
}

########################################
# AMI (Amazon Linux 2)
########################################
data "aws_ssm_parameter" "al2_ami" {
  name = "/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2"
}

########################################
# EC2 Instance
########################################
resource "aws_instance" "n8n" {
  depends_on = [aws_ssm_parameter.n8n_encryption_key]

  ami                         = data.aws_ssm_parameter.al2_ami.value
  instance_type               = var.instance_type
  subnet_id                   = element(data.aws_subnets.default.ids, 0)
  vpc_security_group_ids      = [aws_security_group.n8n.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.ec2_profile.name

  # Enforce IMDSv2 + encrypt root
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_size = 16
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail

    yum update -y
    amazon-linux-extras install -y docker
    systemctl enable docker
    systemctl start docker

    # AWS CLI to fetch SSM parameter
    yum install -y awscli

    # docker-compose v2
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
      -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose

    mkdir -p /opt/n8n && cd /opt/n8n

    # Decrypt the key from SSM
    ENC="$(aws ssm get-parameter --name /n8n/encryption_key --with-decryption --region ${var.region} --query 'Parameter.Value' --output text)"

    # Compose file (unquoted heredoc so bash can expand $ENC variable)
    cat > docker-compose.yml <<YAML
    version: "3.8"
    services:
      n8n:
        image: docker.n8n.io/n8nio/n8n:latest
        restart: unless-stopped
        environment:
          GENERIC_TIMEZONE: "${var.timezone}"
          TZ: "${var.timezone}"
          N8N_ENCRYPTION_KEY: "$${ENC}"
          N8N_RUNNERS_ENABLED: "true"
          N8N_HOST: "${var.domain}"
          N8N_PROTOCOL: "${local.protocol}"
          N8N_PORT: "5678"
          ${local.webhook_env}
          # N8N_BASIC_AUTH_ACTIVE: "true"
          # N8N_BASIC_AUTH_USER: "admin"
          # N8N_BASIC_AUTH_PASSWORD: "change-me"
        volumes:
          - ./n8n_data:/home/node/.n8n
        expose:
          - "5678"

      caddy:
        image: caddy:2
        restart: unless-stopped
        ports:
          - "80:80"
          - "443:443"
        volumes:
          - ./Caddyfile:/etc/caddy/Caddyfile
          - caddy_data:/data
          - caddy_config:/config
        depends_on:
          - n8n

    volumes:
      caddy_data: {}
      caddy_config: {}
    YAML

    # Caddyfile
    cat > Caddyfile <<CADDY
    ${local.caddy_site} {
      encode zstd gzip
      reverse_proxy n8n:5678
    }
    CADDY

    mkdir -p /opt/n8n/n8n_data
    chown -R 1000:1000 /opt/n8n/n8n_data

    /usr/local/bin/docker-compose pull
    /usr/local/bin/docker-compose up -d
  EOT

  tags = { Name = local.project_tag, Project = local.project_tag }
}

########################################
# Elastic IP for stable DNS
########################################
resource "aws_eip" "n8n" {
  domain = "vpc"
  tags   = { Project = local.project_tag }
}

resource "aws_eip_association" "n8n" {
  instance_id   = aws_instance.n8n.id
  allocation_id = aws_eip.n8n.id
}
