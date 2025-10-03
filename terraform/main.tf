terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

########################################
# provider
########################################
provider "aws" {
  profile = var.aws_profile
  region  = var.region
}

########################################
# locals
########################################
locals {
  project_tag = var.project_tag

  # used by n8n to self-advertise external URLs
  protocol = var.domain != "" ? "https" : "http"

  # two env lines only when a domain is set, with correct YAML indentation
  webhook_env = var.domain != "" ? join("\n          ", [
    "WEBHOOK_URL: \"https://${var.domain}/\"",
    "N8N_PROXY_HOPS: \"1\"",
  ]) : ""
}

########################################
# network: default vpc + subnets
########################################
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

########################################
# ami (amazon linux 2023 via ssm param)
########################################
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

########################################
# security group
########################################
resource "aws_security_group" "n8n" {
  name        = "${local.project_tag}-sg"
  description = "n8n access"
  vpc_id      = data.aws_vpc.default.id

  # http (container exposed on host:80)
  ingress {
    description = "http"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # ssh (tighten to your IP if preferred)
  ingress {
    description = "ssh"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "all egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Project = local.project_tag }
}

########################################
# iam: ec2 role with ssm + param store read
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

# allow reading the secure encryption key parameter
data "aws_iam_policy_document" "param_read" {
  statement {
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.n8n_encryption_key.arn]
  }
}

resource "aws_iam_policy" "param_read" {
  name   = "${local.project_tag}-param-read"
  policy = data.aws_iam_policy_document.param_read.json
}

resource "aws_iam_role_policy_attachment" "param_read" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.param_read.arn
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${local.project_tag}-profile"
  role = aws_iam_role.ec2_role.name
}

########################################
# n8n encryption key -> ssm parameter
########################################
resource "random_id" "enc" {
  byte_length = 32
}

resource "aws_ssm_parameter" "n8n_encryption_key" {
  name        = "/${local.project_tag}/encryptionKey"
  description = "n8n encryption key"
  type        = "SecureString"
  value       = random_id.enc.b64_std
  tags        = { Project = local.project_tag }
}

########################################
# ec2 instance
########################################
resource "aws_instance" "n8n" {
  depends_on = [aws_ssm_parameter.n8n_encryption_key]

  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.instance_type
  subnet_id                   = element(data.aws_subnets.default.ids, 0)
  vpc_security_group_ids      = [aws_security_group.n8n.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.ec2_profile.name

  # enforce IMDSv2 + encrypt root
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

    yum update -y || true
    dnf install -y docker
    systemctl enable docker
    systemctl start docker

    dnf install -y awscli

    # docker compose v2
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
      -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose

    # fetch n8n encryption key from ssm
    ENC=$(aws ssm get-parameter \
      --name "/${local.project_tag}/encryptionKey" \
      --with-decryption \
      --query 'Parameter.Value' \
      --output text \
      --region ${var.region})

    mkdir -p /opt/n8n
    cat > /opt/n8n/docker-compose.yml <<'YAML'
    version: "3.8"
    services:
      n8n:
        image: docker.n8n.io/n8nio/n8n:latest
        restart: unless-stopped
        ports:
          - "80:5678"
        environment:
          GENERIC_TIMEZONE: "${var.timezone}"
          TZ: "${var.timezone}"
          N8N_ENCRYPTION_KEY: "__INJECT_ENC__"
          N8N_RUNNERS_ENABLED: "true"
          N8N_HOST: "${var.domain}"
          N8N_PROTOCOL: "${local.protocol}"
          N8N_PORT: "5678"
          ${local.webhook_env}
        volumes:
          - /opt/n8n/data:/home/node/.n8n
    YAML

    # inject ENC safely
    sed -i "s|__INJECT_ENC__|$${ENC}|g" /opt/n8n/docker-compose.yml

    docker-compose -f /opt/n8n/docker-compose.yml up -d
  EOT

  tags = {
    Name    = local.project_tag
    Project = local.project_tag
  }
}

########################################
# elastic ip for stable dns
########################################
resource "aws_eip" "n8n" {
  domain = "vpc"
  tags   = { Project = local.project_tag }
}

resource "aws_eip_association" "n8n" {
  instance_id   = aws_instance.n8n.id
  allocation_id = aws_eip.n8n.id
}
