terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }
}

########################################
# Providers
########################################
provider "aws" {
  profile = var.aws_profile
  region  = var.region
}

# Retrieve EKS cluster info for kubernetes/helm providers
# Note: These data sources are used after the cluster is created
data "aws_eks_cluster" "cluster" {
  name       = aws_eks_cluster.main.name
  depends_on = [aws_eks_cluster.main]
}

data "aws_eks_cluster_auth" "cluster" {
  name       = aws_eks_cluster.main.name
  depends_on = [aws_eks_cluster.main]
}

provider "kubernetes" {
  host                   = try(data.aws_eks_cluster.cluster.endpoint, "")
  cluster_ca_certificate = try(base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data), "")
  token                  = try(data.aws_eks_cluster_auth.cluster.token, "")
}

provider "helm" {
  kubernetes {
    host                   = try(data.aws_eks_cluster.cluster.endpoint, "")
    cluster_ca_certificate = try(base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data), "")
    token                  = try(data.aws_eks_cluster_auth.cluster.token, "")
  }
}

########################################
# Locals
########################################
locals {
  project_tag = var.project_tag
  azs         = slice(data.aws_availability_zones.available.names, 0, 3)
}

# Generate encryption key if not provided
resource "random_id" "enc" {
  byte_length = 32
}

locals {
  # Use provided key if non-empty, otherwise generate random key
  # Unmark sensitive value for comparison and ternary evaluation
  enc_key = nonsensitive(var.n8n_encryption_key) != "" ? nonsensitive(var.n8n_encryption_key) : random_id.enc.hex
  n8n_host_raw = trimspace(var.n8n_host)
  n8n_host     = local.n8n_host_raw != "" ? local.n8n_host_raw : format("%s.local", var.project_tag)
  n8n_protocol = lower(var.n8n_protocol)
  n8n_webhook_url = coalesce(
    var.n8n_webhook_url,
    format("%s://%s/", local.n8n_protocol, local.n8n_host)
  )
  # Environment variables for n8n (used by setup.py when deploying via helm)
  n8n_env = merge({
    N8N_HOST         = local.n8n_host
    N8N_PROTOCOL     = local.n8n_protocol
    N8N_PORT         = tostring(var.n8n_service_port)
    WEBHOOK_URL      = local.n8n_webhook_url
    N8N_PROXY_HOPS   = tostring(var.n8n_proxy_hops)
    GENERIC_TIMEZONE = var.timezone
  }, var.n8n_env_overrides)
}

########################################
# Data Sources
########################################
data "aws_availability_zones" "available" {
  state = "available"
}

########################################
# VPC
########################################
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name                                        = "${local.project_tag}-vpc"
    Project                                     = local.project_tag
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name    = "${local.project_tag}-igw"
    Project = local.project_tag
  }
}

resource "aws_subnet" "public" {
  count                   = length(local.azs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                        = "${local.project_tag}-public-${local.azs[count.index]}"
    Project                                     = local.project_tag
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }
}

resource "aws_subnet" "private" {
  count             = length(local.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 100)
  availability_zone = local.azs[count.index]

  tags = {
    Name                                        = "${local.project_tag}-private-${local.azs[count.index]}"
    Project                                     = local.project_tag
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }
}

resource "aws_eip" "nat" {
  count  = length(local.azs)
  domain = "vpc"

  tags = {
    Name    = "${local.project_tag}-nat-${local.azs[count.index]}"
    Project = local.project_tag
  }
}

resource "aws_nat_gateway" "main" {
  count         = length(local.azs)
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name    = "${local.project_tag}-nat-${local.azs[count.index]}"
    Project = local.project_tag
  }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name    = "${local.project_tag}-public-rt"
    Project = local.project_tag
  }
}

resource "aws_route_table_association" "public" {
  count          = length(local.azs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  count  = length(local.azs)
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[count.index].id
  }

  tags = {
    Name    = "${local.project_tag}-private-rt-${local.azs[count.index]}"
    Project = local.project_tag
  }
}

resource "aws_route_table_association" "private" {
  count          = length(local.azs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

########################################
# EKS Cluster IAM Role
########################################
data "aws_iam_policy_document" "eks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${local.project_tag}-eks-cluster-role"
  assume_role_policy = data.aws_iam_policy_document.eks_assume_role.json

  tags = {
    Project = local.project_tag
  }
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
}

########################################
# EKS Cluster
########################################
resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids              = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_resource_controller,
  ]

  tags = {
    Name    = var.cluster_name
    Project = local.project_tag
  }
}

########################################
# EKS Node Group IAM Role
########################################
data "aws_iam_policy_document" "node_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_nodes" {
  name               = "${local.project_tag}-eks-node-role"
  assume_role_policy = data.aws_iam_policy_document.node_assume_role.json

  tags = {
    Project = local.project_tag
  }
}

resource "aws_iam_role_policy_attachment" "node_worker_policy" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_cni_policy" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "node_registry_policy" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "node_ssm_policy" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Allow reading the n8n encryption key from SSM
resource "aws_iam_role_policy" "node_ssm_get_param" {
  name = "allow-n8n-ssm-get-parameter"
  role = aws_iam_role.eks_nodes.id
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

########################################
# EKS Node Group
########################################
resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${local.project_tag}-node-group"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.private[*].id
  instance_types  = var.node_instance_types

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  update_config {
    max_unavailable = 1
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_worker_policy,
    aws_iam_role_policy_attachment.node_cni_policy,
    aws_iam_role_policy_attachment.node_registry_policy,
    aws_iam_role_policy_attachment.node_ssm_policy,
  ]

  tags = {
    Name    = "${local.project_tag}-node-group"
    Project = local.project_tag
  }
}

########################################
# EBS CSI Driver Addon
########################################
# IAM role for EBS CSI driver
data "aws_iam_policy_document" "ebs_csi_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:kube-system:ebs-csi-controller-sa"]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi_driver" {
  name               = "${local.project_tag}-ebs-csi-driver-role"
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_assume_role.json

  tags = {
    Project = local.project_tag
  }
}

resource "aws_iam_role_policy_attachment" "ebs_csi_driver" {
  role       = aws_iam_role.ebs_csi_driver.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# OIDC provider for EKS
data "tls_certificate" "eks" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer

  tags = {
    Project = local.project_tag
  }
}

# EBS CSI addon
resource "aws_eks_addon" "ebs_csi" {
  cluster_name             = aws_eks_cluster.main.name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = aws_iam_role.ebs_csi_driver.arn

  depends_on = [
    aws_eks_node_group.main,
    aws_iam_role_policy_attachment.ebs_csi_driver,
  ]

  tags = {
    Project = local.project_tag
  }
}

# Default StorageClass for EBS volumes
resource "kubernetes_storage_class" "ebs_gp3" {
  metadata {
    name = "ebs-gp3"
    annotations = {
      "storageclass.kubernetes.io/is-default-class" = "true"
    }
  }

  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true

  parameters = {
    type      = "gp3"
    encrypted = "true"
  }

  depends_on = [aws_eks_addon.ebs_csi]
}

########################################
# SSM Parameter for n8n encryption key
########################################
resource "aws_ssm_parameter" "n8n_encryption_key" {
  name  = "/n8n/encryption_key"
  type  = "SecureString"
  value = local.enc_key

  tags = {
    Project = local.project_tag
  }
}

data "aws_ssm_parameter" "n8n_encryption_key" {
  name            = aws_ssm_parameter.n8n_encryption_key.name
  with_decryption = true

  depends_on = [aws_ssm_parameter.n8n_encryption_key]
}

########################################
# NGINX Ingress Controller (optional)
########################################
resource "helm_release" "nginx_ingress" {
  count = var.enable_nginx_ingress ? 1 : 0

  name       = "ingress-nginx"
  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  namespace  = "ingress-nginx"
  version    = "4.11.3"

  create_namespace = true

  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }

  set {
    name  = "controller.service.annotations.service\\.beta\\.kubernetes\\.io/aws-load-balancer-type"
    value = "nlb"
  }

  depends_on = [
    aws_eks_node_group.main,
    aws_eks_addon.ebs_csi,
  ]
}

########################################
# Note: n8n application deployment is handled by setup.py
# using helm CLI after infrastructure is ready and LoadBalancer
# endpoint is available. This allows proper TLS configuration
# after DNS has been set up.
########################################
