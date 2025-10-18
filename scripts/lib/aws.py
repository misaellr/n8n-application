#!/usr/bin/env python3
"""
AWS-specific deployment logic for n8n on EKS
"""

import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

from .common import Colors, print_error, print_success, print_info


@dataclass
class AWSConfig:
    """AWS EKS deployment configuration"""
    # AWS Settings
    aws_profile: str
    aws_region: str

    # EKS Cluster Settings
    cluster_name: str = "n8n-eks-cluster"
    cluster_version: str = "1.31"

    # Node Group Settings
    node_instance_types: List[str] = None
    node_desired_size: int = 2
    node_min_size: int = 1
    node_max_size: int = 5

    # Application Settings
    n8n_host: str = ""
    n8n_namespace: str = "n8n"
    n8n_persistence_size: str = "10Gi"
    timezone: str = "America/Bahia"
    n8n_encryption_key: str = ""

    # Database Settings
    database_type: str = "sqlite"  # sqlite or postgresql
    rds_instance_class: str = "db.t3.micro"
    rds_allocated_storage: int = 20
    rds_multi_az: bool = False

    # Optional Features
    enable_nginx_ingress: bool = True
    enable_basic_auth: bool = False

    # TLS Settings
    tls_certificate_source: str = "none"  # none, byo, or letsencrypt
    letsencrypt_email: str = ""
    letsencrypt_environment: str = "production"

    def __post_init__(self):
        if self.node_instance_types is None:
            self.node_instance_types = ["t3.medium"]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)

    def to_terraform_vars(self) -> Dict[str, Any]:
        """Convert to Terraform variables format"""
        return {
            'aws_profile': self.aws_profile,
            'region': self.aws_region,
            'cluster_name': self.cluster_name,
            'cluster_version': self.cluster_version,
            'node_instance_types': self.node_instance_types,
            'node_desired_size': self.node_desired_size,
            'node_min_size': self.node_min_size,
            'node_max_size': self.node_max_size,
            'n8n_host': self.n8n_host,
            'n8n_namespace': self.n8n_namespace,
            'n8n_persistence_size': self.n8n_persistence_size,
            'timezone': self.timezone,
            'n8n_encryption_key': self.n8n_encryption_key,
            'database_type': self.database_type,
            'rds_instance_class': self.rds_instance_class,
            'rds_allocated_storage': self.rds_allocated_storage,
            'rds_multi_az': self.rds_multi_az,
            'enable_nginx_ingress': self.enable_nginx_ingress,
            'enable_basic_auth': self.enable_basic_auth,
        }


class AWSAuthValidator:
    """Validates AWS CLI authentication"""

    @staticmethod
    def check_aws_auth(profile: str) -> bool:
        """Check if AWS credentials are configured and valid"""
        try:
            cmd = ['aws', 'sts', 'get-caller-identity', '--profile', profile]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                print_success(f"AWS authentication successful for profile: {profile}")
                return True
            else:
                print_error(f"AWS authentication failed for profile: {profile}")
                print(f"{Colors.FAIL}Error: {result.stderr.strip()}{Colors.ENDC}")
                print(f"\n{Colors.OKCYAN}To configure AWS credentials, run:{Colors.ENDC}")
                print(f"  aws configure --profile {profile}\n")
                return False

        except subprocess.TimeoutExpired:
            print_error("AWS CLI command timed out")
            return False
        except Exception as e:
            print_error(f"Error checking AWS authentication: {e}")
            return False

    @staticmethod
    def get_aws_profiles() -> List[str]:
        """Get list of configured AWS profiles"""
        try:
            cmd = ['aws', 'configure', 'list-profiles']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                profiles = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
                return profiles
            return []

        except Exception:
            return []

    @staticmethod
    def get_aws_regions() -> List[str]:
        """Get list of AWS regions"""
        # Common AWS regions
        return [
            'us-east-1',      # N. Virginia
            'us-east-2',      # Ohio
            'us-west-1',      # N. California
            'us-west-2',      # Oregon
            'eu-west-1',      # Ireland
            'eu-west-2',      # London
            'eu-central-1',   # Frankfurt
            'ap-southeast-1', # Singapore
            'ap-southeast-2', # Sydney
            'ap-northeast-1', # Tokyo
            'ap-northeast-2', # Seoul
            'sa-east-1',      # São Paulo
            'ca-central-1',   # Canada
        ]


class TerraformHelper:
    """Helper for Terraform operations on AWS"""

    def __init__(self, terraform_dir: Path):
        self.terraform_dir = terraform_dir

    def init(self) -> bool:
        """Initialize Terraform"""
        print_info("Initializing Terraform...")
        try:
            result = subprocess.run(
                ['terraform', 'init'],
                cwd=self.terraform_dir,
                capture_output=False,
                text=True
            )
            if result.returncode == 0:
                print_success("Terraform initialized successfully")
                return True
            else:
                print_error("Terraform init failed")
                return False
        except Exception as e:
            print_error(f"Error running terraform init: {e}")
            return False

    def plan(self, var_file: Optional[str] = None) -> bool:
        """Run Terraform plan"""
        print_info("Running Terraform plan...")
        cmd = ['terraform', 'plan']
        if var_file:
            cmd.extend(['-var-file', var_file])

        try:
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=False,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            print_error(f"Error running terraform plan: {e}")
            return False

    def apply(self, auto_approve: bool = False) -> bool:
        """Run Terraform apply"""
        print_info("Applying Terraform configuration...")
        cmd = ['terraform', 'apply']
        if auto_approve:
            cmd.append('-auto-approve')

        try:
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=False,
                text=True
            )
            if result.returncode == 0:
                print_success("Terraform apply completed successfully")
                return True
            else:
                print_error("Terraform apply failed")
                return False
        except Exception as e:
            print_error(f"Error running terraform apply: {e}")
            return False

    def destroy(self, auto_approve: bool = False) -> bool:
        """Run Terraform destroy"""
        print_info("Destroying Terraform-managed infrastructure...")
        cmd = ['terraform', 'destroy']
        if auto_approve:
            cmd.append('-auto-approve')

        try:
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=False,
                text=True
            )
            if result.returncode == 0:
                print_success("Terraform destroy completed successfully")
                return True
            else:
                print_error("Terraform destroy failed")
                return False
        except Exception as e:
            print_error(f"Error running terraform destroy: {e}")
            return False

    def output(self, output_name: str) -> Optional[str]:
        """Get Terraform output value"""
        try:
            result = subprocess.run(
                ['terraform', 'output', '-raw', output_name],
                cwd=self.terraform_dir,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def write_tfvars(self, config: AWSConfig) -> bool:
        """Write terraform.tfvars file"""
        tfvars_path = self.terraform_dir / "terraform.tfvars"

        try:
            with open(tfvars_path, 'w') as f:
                f.write("# AWS EKS Deployment Configuration\n")
                f.write(f"# Generated automatically - do not edit manually\n\n")

                # AWS Configuration
                f.write("# AWS Configuration\n")
                f.write(f'aws_profile = "{config.aws_profile}"\n')
                f.write(f'region = "{config.aws_region}"\n\n')

                # EKS Configuration
                f.write("# EKS Cluster Configuration\n")
                f.write(f'cluster_name = "{config.cluster_name}"\n')
                f.write(f'cluster_version = "{config.cluster_version}"\n\n')

                # Node Group
                f.write("# Node Group Configuration\n")
                f.write(f'node_instance_types = {config.node_instance_types}\n')
                f.write(f'node_desired_size = {config.node_desired_size}\n')
                f.write(f'node_min_size = {config.node_min_size}\n')
                f.write(f'node_max_size = {config.node_max_size}\n\n')

                # Application Settings
                f.write("# Application Configuration\n")
                f.write(f'n8n_host = "{config.n8n_host}"\n')
                f.write(f'n8n_namespace = "{config.n8n_namespace}"\n')
                f.write(f'n8n_persistence_size = "{config.n8n_persistence_size}"\n')
                f.write(f'timezone = "{config.timezone}"\n')
                if config.n8n_encryption_key:
                    f.write(f'n8n_encryption_key = "{config.n8n_encryption_key}"\n')
                f.write('\n')

                # Database Configuration
                f.write("# Database Configuration\n")
                f.write(f'database_type = "{config.database_type}"\n')
                if config.database_type == "postgresql":
                    f.write(f'rds_instance_class = "{config.rds_instance_class}"\n')
                    f.write(f'rds_allocated_storage = {config.rds_allocated_storage}\n')
                    f.write(f'rds_multi_az = {str(config.rds_multi_az).lower()}\n')
                f.write('\n')

                # Optional Features
                f.write("# Optional Features\n")
                f.write(f'enable_nginx_ingress = {str(config.enable_nginx_ingress).lower()}\n')
                f.write(f'enable_basic_auth = {str(config.enable_basic_auth).lower()}\n')

            print_success(f"Terraform configuration written to {tfvars_path}")
            return True

        except Exception as e:
            print_error(f"Failed to write terraform.tfvars: {e}")
            return False


def configure_kubectl_for_eks(cluster_name: str, region: str, profile: str) -> bool:
    """Configure kubectl to use EKS cluster"""
    print_info(f"Configuring kubectl for EKS cluster: {cluster_name}")

    try:
        cmd = [
            'aws', 'eks', 'update-kubeconfig',
            '--region', region,
            '--name', cluster_name,
            '--profile', profile
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print_success("kubectl configured successfully")
            return True
        else:
            print_error(f"Failed to configure kubectl: {result.stderr}")
            return False

    except Exception as e:
        print_error(f"Error configuring kubectl: {e}")
        return False
