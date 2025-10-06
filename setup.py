#!/usr/bin/env python3
"""
N8N EKS Deployment Setup CLI
Automates the setup and deployment of n8n on AWS EKS using Terraform and Helm
"""

import os
import sys
import json
import subprocess
import shutil
import tempfile
import secrets
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import signal

# ANSI color codes
class Colors:
    # Liferay Lexicon-inspired color palette
    HEADER = '\033[94m'    # Light Blue for headers
    OKBLUE = '\033[1;94m'   # Bold Light Blue for branding elements
    OKCYAN = '\033[96m'    # Cyan for informational text
    OKGREEN = '\033[92m'   # Green for success messages
    WARNING = '\033[93m'   # Yellow for warnings
    FAIL = '\033[91m'      # Red for errors
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class SetupInterrupted(Exception):
    """Raised when user interrupts the setup process"""
    pass

class DeploymentConfig:
    """Stores all configuration for the EKS deployment"""
    def __init__(self):
        self.aws_profile: Optional[str] = None
        self.aws_region: Optional[str] = None
        self.cluster_name: str = "n8n-eks-cluster"
        self.node_instance_types: list = ["t3.medium"]
        self.node_desired_size: int = 1
        self.node_min_size: int = 1
        self.node_max_size: int = 2
        self.n8n_namespace: str = "n8n"
        self.n8n_host: str = ""
        self.timezone: str = "America/Bahia"
        self.n8n_encryption_key: str = ""
        self.n8n_persistence_size: str = "10Gi"

        # TLS Configuration
        self.tls_certificate_source: str = "none"  # "none", "byo", or "letsencrypt"
        self.tls_certificate_crt: str = ""  # PEM content for BYO
        self.tls_certificate_key: str = ""  # PEM content for BYO
        self.letsencrypt_email: str = ""
        self.letsencrypt_environment: str = "production"  # "staging" or "production"

        # Database Configuration
        self.database_type: str = "sqlite"  # "sqlite" or "postgresql"
        self.rds_instance_class: str = "db.t3.micro"
        self.rds_allocated_storage: int = 20
        self.rds_multi_az: bool = False

        # Basic Authentication Configuration
        self.enable_basic_auth: bool = False
        self.basic_auth_username: str = "admin"
        self.basic_auth_password: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'aws_profile': self.aws_profile,
            'aws_region': self.aws_region,
            'cluster_name': self.cluster_name,
            'node_instance_types': self.node_instance_types,
            'node_desired_size': self.node_desired_size,
            'node_min_size': self.node_min_size,
            'node_max_size': self.node_max_size,
            'n8n_namespace': self.n8n_namespace,
            'n8n_host': self.n8n_host,
            'timezone': self.timezone,
            'n8n_persistence_size': self.n8n_persistence_size,
            'tls_certificate_source': self.tls_certificate_source,
            'letsencrypt_email': self.letsencrypt_email,
            'letsencrypt_environment': self.letsencrypt_environment,
            'database_type': self.database_type,
            'rds_instance_class': self.rds_instance_class,
            'rds_allocated_storage': self.rds_allocated_storage,
            'rds_multi_az': self.rds_multi_az,
            'enable_basic_auth': self.enable_basic_auth,
        }

class DependencyChecker:
    """Checks for required CLI tools for EKS deployment"""

    REQUIRED_TOOLS = {
        'terraform': {
            'command': 'terraform version',
            'install_url': 'https://developer.hashicorp.com/terraform/downloads',
            'description': 'Infrastructure as Code tool'
        },
        'aws': {
            'command': 'aws --version',
            'install_url': 'https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html',
            'description': 'AWS Command Line Interface'
        },
        'helm': {
            'command': 'helm version',
            'install_url': 'https://helm.sh/docs/intro/install/',
            'description': 'Kubernetes package manager'
        },
        'kubectl': {
            'command': 'kubectl version --client',
            'install_url': 'https://kubernetes.io/docs/tasks/tools/',
            'description': 'Kubernetes command-line tool'
        }
    }

    @staticmethod
    def check_python_version() -> Tuple[bool, str]:
        """Check if Python version is 3.7 or higher"""
        major, minor = sys.version_info[:2]
        current_version = f"{major}.{minor}"

        if major < 3 or (major == 3 and minor < 7):
            return False, f"Python {current_version} (requires 3.7+)"
        return True, f"Python {current_version}"

    @staticmethod
    def check_tool(tool_name: str) -> bool:
        """Check if a tool is installed"""
        return shutil.which(tool_name) is not None

    @classmethod
    def check_all_dependencies(cls) -> Tuple[bool, list]:
        """Check all required dependencies for EKS deployment"""
        missing = []

        print(f"\n{Colors.HEADER}🔍 Checking dependencies for EKS deployment...{Colors.ENDC}")

        # Check Python version first
        python_ok, python_info = cls.check_python_version()
        if python_ok:
            print(f"{Colors.OKGREEN}✓{Colors.ENDC} {python_info}")
        else:
            print(f"{Colors.FAIL}✗{Colors.ENDC} {python_info}")
            print(f"\n{Colors.FAIL}Python 3.7 or higher is required!{Colors.ENDC}")
            print(f"Current version: {python_info}")
            print(f"Please upgrade Python: {Colors.OKCYAN}https://www.python.org/downloads/{Colors.ENDC}\n")
            return False, [('python', {'description': 'Python 3.7+', 'install_url': 'https://www.python.org/downloads/'})]

        # Check all required tools
        for tool, info in cls.REQUIRED_TOOLS.items():
            if cls.check_tool(tool):
                print(f"{Colors.OKGREEN}✓{Colors.ENDC} {tool} - installed")
            else:
                print(f"{Colors.FAIL}✗{Colors.ENDC} {tool} - NOT installed")
                missing.append((tool, info))

        if missing:
            print(f"\n{Colors.WARNING}Missing dependencies detected!{Colors.ENDC}")
            print("\nPlease install the following tools:\n")
            for tool, info in missing:
                print(f"  {Colors.BOLD}{tool}{Colors.ENDC}: {info['description']}")
                print(f"    Installation: {Colors.OKCYAN}{info['install_url']}{Colors.ENDC}\n")
            return False, missing

        print(f"\n{Colors.OKGREEN}✓ All dependencies satisfied{Colors.ENDC}")
        return True, []

class CertificateValidator:
    """Validates TLS certificates in PEM format"""

    @staticmethod
    def validate_pem_file(file_path: str, cert_type: str = "certificate") -> Tuple[bool, str]:
        """Validate a PEM file and return its content"""
        try:
            path = Path(file_path).expanduser()
            if not path.exists():
                return False, f"File not found: {file_path}"

            if not path.is_file():
                return False, f"Not a file: {file_path}"

            content = path.read_text()

            # Basic PEM format validation
            if cert_type == "certificate":
                if "-----BEGIN CERTIFICATE-----" not in content:
                    return False, "Not a valid PEM certificate (missing BEGIN CERTIFICATE)"
                if "-----END CERTIFICATE-----" not in content:
                    return False, "Not a valid PEM certificate (missing END CERTIFICATE)"
            elif cert_type == "key":
                # Support various private key formats
                key_markers = [
                    "-----BEGIN PRIVATE KEY-----",
                    "-----BEGIN RSA PRIVATE KEY-----",
                    "-----BEGIN EC PRIVATE KEY-----"
                ]
                if not any(marker in content for marker in key_markers):
                    return False, "Not a valid PEM private key"

            return True, content

        except Exception as e:
            return False, f"Error reading file: {str(e)}"

    @staticmethod
    def validate_email(email: str) -> bool:
        """Simple email validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

class AWSAuthChecker:
    """Handles AWS authentication verification"""

    @staticmethod
    def get_available_profiles() -> list:
        """Get list of configured AWS profiles"""
        try:
            result = subprocess.run(
                ['aws', 'configure', 'list-profiles'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
            return []
        except Exception:
            return []

    @staticmethod
    def verify_credentials(profile: Optional[str] = None, region: Optional[str] = None) -> Tuple[bool, str]:
        """Verify AWS credentials work"""
        cmd = ['aws', 'sts', 'get-caller-identity']

        env = os.environ.copy()
        if profile:
            env['AWS_PROFILE'] = profile
        if region:
            env['AWS_DEFAULT_REGION'] = region

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )

            if result.returncode == 0:
                identity = json.loads(result.stdout)
                account_id = identity.get('Account', 'unknown')
                user_arn = identity.get('Arn', 'unknown')
                return True, f"Account: {account_id}, User: {user_arn}"
            else:
                return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "AWS authentication timed out"
        except Exception as e:
            return False, str(e)

class ConfigurationPrompt:
    """Handles interactive configuration prompts"""

    def __init__(self):
        self.config = DeploymentConfig()
        self._interrupted = False

        # Setup interrupt handler
        signal.signal(signal.SIGINT, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        self._interrupted = True
        raise SetupInterrupted("\n\nSetup interrupted by user")

    @staticmethod
    def prompt(question: str, default: str = "", required: bool = False) -> str:
        """Prompt user for input"""
        if default:
            question_text = f"{question} [{Colors.OKCYAN}{default}{Colors.ENDC}]: "
        else:
            question_text = f"{question}: "

        while True:
            try:
                answer = input(question_text).strip()
                if not answer:
                    answer = default

                if required and not answer:
                    print(f"{Colors.WARNING}This field is required{Colors.ENDC}")
                    continue

                return answer
            except EOFError:
                raise SetupInterrupted("\nSetup interrupted")

    @staticmethod
    def prompt_choice(question: str, choices: list, default: int = 0) -> str:
        """Prompt user to choose from a list"""
        print(f"\n{question}")
        for i, choice in enumerate(choices, 1):
            default_marker = " (default)" if i - 1 == default else ""
            print(f"  {i}. {choice}{default_marker}")

        while True:
            try:
                answer = input(f"Choose [1-{len(choices)}]: ").strip()
                if not answer:
                    return choices[default]

                choice_num = int(answer)
                if 1 <= choice_num <= len(choices):
                    return choices[choice_num - 1]
                else:
                    print(f"{Colors.WARNING}Please enter a number between 1 and {len(choices)}{Colors.ENDC}")
            except ValueError:
                print(f"{Colors.WARNING}Please enter a valid number{Colors.ENDC}")
            except EOFError:
                raise SetupInterrupted("\nSetup interrupted")

    @staticmethod
    def prompt_yes_no(question: str, default: bool = True) -> bool:
        """Prompt for yes/no answer"""
        default_text = "Y/n" if default else "y/N"
        while True:
            try:
                answer = input(f"{question} [{default_text}]: ").strip().lower()
                if not answer:
                    return default
                if answer in ['y', 'yes']:
                    return True
                if answer in ['n', 'no']:
                    return False
                print(f"{Colors.WARNING}Please answer 'y' or 'n'{Colors.ENDC}")
            except EOFError:
                raise SetupInterrupted("\nSetup interrupted")

    def collect_configuration(self, skip_tls: bool = True) -> DeploymentConfig:
        """Collect all configuration from user

        Args:
            skip_tls: If True, skip TLS configuration (TLS will be configured after LoadBalancer is ready)
        """
        print(f"\n{Colors.HEADER}{Colors.BOLD}N8N EKS Deployment Configuration{Colors.ENDC}")
        print("=" * 60)

        # AWS Configuration
        print(f"\n{Colors.BOLD}AWS Configuration{Colors.ENDC}")

        # Get available profiles
        profiles = AWSAuthChecker.get_available_profiles()
        if profiles:
            print(f"\nAvailable AWS profiles: {', '.join(profiles)}")
            self.config.aws_profile = self.prompt(
                "AWS Profile to use",
                default=profiles[0] if profiles else "",
                required=True
            )
        else:
            print(f"\n{Colors.WARNING}No AWS profiles found in ~/.aws/config{Colors.ENDC}")
            if self.prompt_yes_no("Use default AWS credentials?", default=True):
                self.config.aws_profile = "default"
            else:
                print("\nPlease configure AWS CLI first:")
                print(f"  {Colors.OKCYAN}aws configure{Colors.ENDC}")
                raise SetupInterrupted("AWS configuration required")

        # AWS Region
        common_regions = [
            "us-east-1", "us-east-2", "us-west-1", "us-west-2",
            "eu-west-1", "eu-central-1", "ap-southeast-1", "ap-southeast-2"
        ]
        print(f"\nCommon regions: {', '.join(common_regions)}")
        self.config.aws_region = self.prompt(
            "AWS Region",
            default="us-east-1",
            required=True
        )

        # Verify AWS credentials
        print(f"\n{Colors.HEADER}🔐 Verifying AWS credentials...{Colors.ENDC}")
        success, message = AWSAuthChecker.verify_credentials(
            self.config.aws_profile,
            self.config.aws_region
        )

        if success:
            print(f"{Colors.OKGREEN}✓ AWS credentials verified{Colors.ENDC}")
            print(f"  {message}")
        else:
            print(f"{Colors.FAIL}✗ AWS authentication failed{Colors.ENDC}")
            print(f"  {message}")
            print(f"\n{Colors.WARNING}Please authenticate with AWS:{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}aws configure --profile {self.config.aws_profile}{Colors.ENDC}")
            raise SetupInterrupted("AWS authentication required")

        # EKS Cluster Configuration
        print(f"\n{Colors.BOLD}EKS Cluster Configuration{Colors.ENDC}")

        self.config.cluster_name = self.prompt(
            "EKS Cluster Name",
            default="n8n-eks-cluster"
        )

        node_types = ["t3.small", "t3.medium", "t3.large"]
        print(f"\nRecommended node types: {', '.join(node_types)}")
        node_type = self.prompt(
            "Node Instance Type",
            default="t3.medium"
        )
        self.config.node_instance_types = [node_type]

        self.config.node_desired_size = int(self.prompt(
            "Desired number of nodes",
            default="1"
        ))

        self.config.node_min_size = int(self.prompt(
            "Minimum number of nodes",
            default="1"
        ))

        self.config.node_max_size = int(self.prompt(
            "Maximum number of nodes",
            default="2"
        ))

        # N8N Configuration
        print(f"\n{Colors.BOLD}N8N Configuration{Colors.ENDC}")

        self.config.n8n_namespace = self.prompt(
            "Kubernetes namespace for n8n",
            default="n8n"
        )

        self.config.n8n_host = self.prompt(
            "N8N Hostname (FQDN for ingress)",
            default="n8n.example.com",
            required=True
        )

        self.config.n8n_persistence_size = self.prompt(
            "Persistent volume size (e.g., 10Gi, 20Gi)",
            default="10Gi"
        )

        # Timezone
        common_timezones = [
            "America/New_York", "America/Chicago", "America/Los_Angeles",
            "America/Bahia", "Europe/London", "Europe/Paris", "Asia/Tokyo"
        ]
        print(f"\nCommon timezones: {', '.join(common_timezones)}")
        self.config.timezone = self.prompt(
            "Timezone",
            default="America/Bahia"
        )

        # Encryption key
        if self.prompt_yes_no("\nGenerate a new n8n encryption key?", default=True):
            self.config.n8n_encryption_key = secrets.token_hex(32)
            print(f"{Colors.OKGREEN}✓ Generated new encryption key{Colors.ENDC}")
        else:
            self.config.n8n_encryption_key = self.prompt(
                "Enter existing n8n encryption key (64 hex characters)",
                required=True
            )

        # Database Configuration
        print(f"\n{Colors.BOLD}Database Configuration{Colors.ENDC}")
        print("\nChoose database backend for n8n:")
        db_choice = self.prompt_choice(
            "Database Type",
            [
                "SQLite (file-based, simpler, lower cost ~$1/month)",
                "PostgreSQL (RDS, production-grade, scalable, ~$15-60/month)"
            ],
            default=0
        )

        if "PostgreSQL" in db_choice:
            self.config.database_type = "postgresql"

            print(f"\n{Colors.BOLD}RDS PostgreSQL Configuration{Colors.ENDC}")

            # RDS instance class
            rds_instances = ["db.t3.micro", "db.t3.small", "db.t3.medium"]
            print(f"\nAvailable instance classes: {', '.join(rds_instances)}")
            print(f"  • db.t3.micro:  ~$15/month (single-AZ), ~$30/month (multi-AZ)")
            print(f"  • db.t3.small:  ~$30/month (single-AZ), ~$60/month (multi-AZ)")
            print(f"  • db.t3.medium: ~$60/month (single-AZ), ~$120/month (multi-AZ)")

            self.config.rds_instance_class = self.prompt(
                "RDS Instance Class",
                default="db.t3.micro"
            )

            # Storage
            storage = self.prompt(
                "Allocated storage (GB)",
                default="20"
            )
            self.config.rds_allocated_storage = int(storage)

            # Multi-AZ
            self.config.rds_multi_az = self.prompt_yes_no(
                "Enable Multi-AZ deployment (high availability)?",
                default=False
            )

            print(f"\n{Colors.OKGREEN}✓ PostgreSQL RDS will be provisioned{Colors.ENDC}")
        else:
            self.config.database_type = "sqlite"
            print(f"\n{Colors.OKGREEN}✓ SQLite will be used (file-based on EBS volume){Colors.ENDC}")

        # Show summary
        self._show_summary()

        if not self.prompt_yes_no("\nProceed with this configuration?", default=True):
            raise SetupInterrupted("Configuration cancelled by user")

        return self.config

    def _show_summary(self):
        """Display configuration summary"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}Configuration Summary{Colors.ENDC}")
        print("=" * 60)
        print(f"Deployment:      {Colors.OKCYAN}AWS EKS (Kubernetes){Colors.ENDC}")
        print(f"AWS Profile:     {Colors.OKCYAN}{self.config.aws_profile}{Colors.ENDC}")
        print(f"AWS Region:      {Colors.OKCYAN}{self.config.aws_region}{Colors.ENDC}")
        print(f"Cluster Name:    {Colors.OKCYAN}{self.config.cluster_name}{Colors.ENDC}")
        print(f"Node Type:       {Colors.OKCYAN}{self.config.node_instance_types[0]}{Colors.ENDC}")
        print(f"Node Count:      {Colors.OKCYAN}{self.config.node_desired_size} (min: {self.config.node_min_size}, max: {self.config.node_max_size}){Colors.ENDC}")
        print(f"Namespace:       {Colors.OKCYAN}{self.config.n8n_namespace}{Colors.ENDC}")
        print(f"N8N Host:        {Colors.OKCYAN}{self.config.n8n_host}{Colors.ENDC}")
        print(f"PVC Size:        {Colors.OKCYAN}{self.config.n8n_persistence_size}{Colors.ENDC}")
        print(f"Timezone:        {Colors.OKCYAN}{self.config.timezone}{Colors.ENDC}")
        print(f"Encryption Key:  {Colors.OKCYAN}{'*' * 20} (hidden){Colors.ENDC}")
        print(f"Database Type:   {Colors.OKCYAN}{self.config.database_type.upper()}{Colors.ENDC}")
        if self.config.database_type == "postgresql":
            print(f"  RDS Instance:  {Colors.OKCYAN}{self.config.rds_instance_class}{Colors.ENDC}")
            print(f"  RDS Storage:   {Colors.OKCYAN}{self.config.rds_allocated_storage}GB{Colors.ENDC}")
            print(f"  RDS Multi-AZ:  {Colors.OKCYAN}{'Yes' if self.config.rds_multi_az else 'No'}{Colors.ENDC}")
        print("=" * 60)
        print(f"\n{Colors.WARNING}Note: TLS and Basic Auth will be configured after deployment{Colors.ENDC}")

class FileUpdater:
    """Handles updating Terraform and Helm configuration files"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.terraform_dir = base_dir / "terraform"
        self.helm_dir = base_dir / "helm"
        self.backup_dir: Optional[Path] = None

    def create_backup(self) -> Path:
        """Create backup of configuration files"""
        self.backup_dir = Path(tempfile.mkdtemp(prefix="n8n-backup-"))

        # Backup terraform files
        terraform_backup = self.backup_dir / "terraform"
        terraform_backup.mkdir(parents=True)
        for file in self.terraform_dir.glob("*.tf"):
            shutil.copy2(file, terraform_backup / file.name)

        # Backup helm files
        helm_backup = self.backup_dir / "helm"
        shutil.copytree(self.helm_dir, helm_backup, dirs_exist_ok=True)

        print(f"{Colors.OKGREEN}✓ Created backup at {self.backup_dir}{Colors.ENDC}")
        return self.backup_dir

    def restore_backup(self):
        """Restore files from backup"""
        if not self.backup_dir or not self.backup_dir.exists():
            return

        print(f"\n{Colors.WARNING}Restoring configuration files from backup...{Colors.ENDC}")

        # Restore terraform
        for file in (self.backup_dir / "terraform").glob("*.tf"):
            shutil.copy2(file, self.terraform_dir / file.name)

        # Restore helm
        for file in (self.backup_dir / "helm").rglob("*"):
            if file.is_file():
                rel_path = file.relative_to(self.backup_dir / "helm")
                dest = self.helm_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)

        print(f"{Colors.OKGREEN}✓ Configuration restored{Colors.ENDC}")

    def cleanup_backup(self):
        """Remove backup directory"""
        if self.backup_dir and self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)

    def update_terraform_variables(self, config: DeploymentConfig):
        """Update Terraform variables file"""
        variables_file = self.terraform_dir / "variables.tf"

        content = variables_file.read_text()

        # Update defaults
        content = self._update_variable_default(content, "aws_profile", config.aws_profile)
        content = self._update_variable_default(content, "region", config.aws_region)
        content = self._update_variable_default(content, "instance_type", config.instance_type)
        content = self._update_variable_default(content, "domain", config.domain)
        content = self._update_variable_default(content, "timezone", config.timezone)

        variables_file.write_text(content)
        print(f"{Colors.OKGREEN}✓ Updated terraform/variables.tf{Colors.ENDC}")

    def create_terraform_tfvars(self, config: DeploymentConfig):
        """Create terraform.tfvars for EKS infrastructure deployment"""
        tfvars_file = self.terraform_dir / "terraform.tfvars"

        # Build tfvars content - infrastructure only, no TLS
        lines = [
            "# Auto-generated by setup.py - N8N EKS Infrastructure",
            f'aws_profile        = "{config.aws_profile}"',
            f'region             = "{config.aws_region}"',
            f'cluster_name       = "{config.cluster_name}"',
            f'node_instance_types = {json.dumps(config.node_instance_types)}',
            f'node_desired_size  = {config.node_desired_size}',
            f'node_min_size      = {config.node_min_size}',
            f'node_max_size      = {config.node_max_size}',
            f'n8n_host           = "{config.n8n_host}"',
            f'timezone           = "{config.timezone}"',
            f'n8n_encryption_key = "{config.n8n_encryption_key}"',
            f'n8n_namespace      = "{config.n8n_namespace}"',
            f'n8n_persistence_size = "{config.n8n_persistence_size}"',
            "",
            "# Database Configuration",
            f'database_type      = "{config.database_type}"',
        ]

        # Add RDS configuration if PostgreSQL is selected
        if config.database_type == "postgresql":
            lines.extend([
                f'rds_instance_class = "{config.rds_instance_class}"',
                f'rds_allocated_storage = {config.rds_allocated_storage}',
                f'rds_multi_az       = {"true" if config.rds_multi_az else "false"}',
            ])

        lines.extend([
            "",
            "# Basic Authentication Configuration",
            f'enable_basic_auth  = {"true" if config.enable_basic_auth else "false"}',
            "",
        ])

        content = "\n".join(lines)
        tfvars_file.write_text(content)
        print(f"{Colors.OKGREEN}✓ Created terraform/terraform.tfvars{Colors.ENDC}")

    def update_helm_values(self, config: DeploymentConfig):
        """Update Helm values file"""
        values_file = self.helm_dir / "values.yaml"

        content = values_file.read_text()

        # Update values
        content = self._replace_yaml_value(content, "  host:", config.n8n_host)
        content = self._replace_yaml_value(content, "  N8N_HOST:", config.n8n_host)
        content = self._replace_yaml_value(content, "  WEBHOOK_URL:", f"https://{config.n8n_host}/")
        content = self._replace_yaml_value(content, "  GENERIC_TIMEZONE:", config.timezone)
        content = self._replace_yaml_value(content, "  TZ:", config.timezone)

        # Update encryption key in envSecrets
        content = self._replace_yaml_value(
            content,
            "  N8N_ENCRYPTION_KEY:",
            config.n8n_encryption_key,
            in_section="envSecrets"
        )

        values_file.write_text(content)
        print(f"{Colors.OKGREEN}✓ Updated helm/values.yaml{Colors.ENDC}")

    @staticmethod
    def _update_variable_default(content: str, var_name: str, value: str) -> str:
        """Update a Terraform variable default value"""
        import re

        # Match variable block and update default
        pattern = rf'(variable\s+"{var_name}"\s+\{{[^}}]*default\s*=\s*)"[^"]*"'
        replacement = rf'\1"{value}"'

        return re.sub(pattern, replacement, content, flags=re.DOTALL)

    @staticmethod
    def _replace_yaml_value(content: str, key: str, value: str, in_section: str = None) -> str:
        """Replace a YAML value"""
        import re

        # Escape special regex characters in key
        escaped_key = re.escape(key)

        # Pattern to match key with quoted or unquoted value
        pattern = rf'^({escaped_key}\s+)["\']?[^"\'\n]*["\']?$'
        replacement = rf'\1"{value}"'

        return re.sub(pattern, replacement, content, flags=re.MULTILINE)

    def apply_configuration(self, config: DeploymentConfig):
        """Apply configuration to all files for EKS deployment"""
        print(f"\n{Colors.HEADER}📝 Updating configuration files...{Colors.ENDC}")

        self.create_backup()

        try:
            # Create terraform.tfvars
            self.create_terraform_tfvars(config)

            print(f"{Colors.OKGREEN}✓ All configuration files updated{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}✗ Error updating files: {e}{Colors.ENDC}")
            self.restore_backup()
            raise


def load_existing_configuration(script_dir: Path) -> DeploymentConfig:
    """Load deployment values from terraform/terraform.tfvars"""
    tfvars_path = script_dir / "terraform" / "terraform.tfvars"

    if not tfvars_path.exists():
        raise FileNotFoundError("terraform/terraform.tfvars not found; run initial setup first")

    config = DeploymentConfig()

    for raw_line in tfvars_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = [part.strip() for part in line.split('=', 1)]
        value = value.rstrip(',')

        parsed: Any = value
        if value.startswith('"') and value.endswith('"'):
            parsed = value[1:-1]
        else:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = value

        if key == 'aws_profile':
            config.aws_profile = str(parsed)
        elif key == 'region':
            config.aws_region = str(parsed)
        elif key == 'cluster_name':
            config.cluster_name = str(parsed)
        elif key == 'node_instance_types':
            config.node_instance_types = list(parsed) if isinstance(parsed, list) else [str(parsed)]
        elif key == 'node_desired_size':
            config.node_desired_size = int(parsed)
        elif key == 'n8n_host':
            config.n8n_host = str(parsed)
        elif key == 'timezone':
            config.timezone = str(parsed)
        elif key == 'n8n_encryption_key':
            config.n8n_encryption_key = str(parsed)

    if not config.n8n_host:
        raise ValueError("n8n_host is missing in terraform.tfvars")

    return config

class TerraformRunner:
    """Handles Terraform execution"""

    def __init__(self, terraform_dir: Path):
        self.terraform_dir = terraform_dir

    def run_command(self, args: list, interactive: bool = False) -> Tuple[bool, str]:
        """Run a terraform command"""
        cmd = ['terraform'] + args

        try:
            if interactive:
                # Run interactively for apply/destroy
                result = subprocess.run(
                    cmd,
                    cwd=self.terraform_dir,
                    text=True
                )
                return result.returncode == 0, ""
            else:
                result = subprocess.run(
                    cmd,
                    cwd=self.terraform_dir,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def init(self) -> bool:
        """Initialize Terraform"""
        print(f"\n{Colors.HEADER}🔧 Initializing Terraform...{Colors.ENDC}")
        success, output = self.run_command(['init'])

        if success:
            print(f"{Colors.OKGREEN}✓ Terraform initialized{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}✗ Terraform init failed{Colors.ENDC}")
            print(output)

        return success

    def plan(self, display_output: bool = True) -> Tuple[bool, str]:
        """Run Terraform plan and optionally display output

        Returns:
            Tuple of (success, output_text)
        """
        print(f"\n{Colors.HEADER}📋 Running Terraform plan...{Colors.ENDC}")
        success, output = self.run_command(['plan', '-no-color'])

        if success:
            print(f"{Colors.OKGREEN}✓ Terraform plan completed{Colors.ENDC}")
            if display_output:
                print(f"\n{Colors.BOLD}Plan Summary:{Colors.ENDC}")
                print("=" * 60)
                print(output)
                print("=" * 60)
        else:
            print(f"{Colors.FAIL}✗ Terraform plan failed{Colors.ENDC}")
            print(output)

        return success, output

    def apply(self) -> bool:
        """Apply Terraform configuration"""
        print(f"\n{Colors.HEADER}🚀 Applying Terraform configuration...{Colors.ENDC}")
        print(f"{Colors.WARNING}This will create real AWS resources and may incur costs.{Colors.ENDC}")

        success, _ = self.run_command(['apply'], interactive=True)

        if success:
            print(f"\n{Colors.OKGREEN}✓ Terraform apply completed{Colors.ENDC}")
        else:
            print(f"\n{Colors.FAIL}✗ Terraform apply failed{Colors.ENDC}")

        return success

    def get_outputs(self) -> Dict[str, str]:
        """Get Terraform outputs"""
        success, output = self.run_command(['output', '-json'])

        if success:
            try:
                outputs = json.loads(output)
                return {k: v.get('value', '') for k, v in outputs.items()}
            except json.JSONDecodeError:
                return {}

        return {}

class HelmRunner:
    """Handles Helm execution"""

    def __init__(self, helm_dir: Path):
        self.helm_dir = helm_dir

    def run_command(self, args: list, interactive: bool = False) -> Tuple[bool, str]:
        """Run a helm command"""
        cmd = ['helm'] + args

        try:
            if interactive:
                result = subprocess.run(cmd, text=True)
                return result.returncode == 0, ""
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def deploy_n8n(self, config: DeploymentConfig, encryption_key: str, namespace: str = "n8n",
                    tls_enabled: bool = False, db_config: Dict[str, Any] = None) -> bool:
        """Deploy n8n via Helm without TLS initially

        Args:
            config: Deployment configuration
            encryption_key: N8N encryption key
            namespace: Kubernetes namespace
            tls_enabled: Whether to enable TLS
            db_config: Database configuration from Terraform outputs (for PostgreSQL)
        """
        print(f"\n{Colors.HEADER}🎯 Deploying n8n application...{Colors.ENDC}")

        # Build helm values
        values_args = [
            'install', 'n8n', str(self.helm_dir),
            '--namespace', namespace,
            '--create-namespace',
            '--set', f'ingress.enabled=true',
            '--set', f'ingress.className=nginx',
            '--set', f'ingress.host={config.n8n_host}',
            '--set', 'ingress.allowLoadBalancerHostname=true',
            '--set', f'ingress.tls.enabled={str(tls_enabled).lower()}',
            '--set', f'env.N8N_HOST={config.n8n_host}',
            '--set', f'env.N8N_PROTOCOL={"https" if tls_enabled else "http"}',
            '--set', f'env.GENERIC_TIMEZONE={config.timezone}',
            '--set', f'env.TZ={config.timezone}',
            '--set-string', f'envSecrets.N8N_ENCRYPTION_KEY={encryption_key}',
            '--set', f'persistence.size={config.n8n_persistence_size}',
        ]

        # Add database configuration if PostgreSQL is selected
        if db_config and db_config.get('database_type') == 'postgresql':
            print(f"{Colors.OKCYAN}  Configuring PostgreSQL database connection...{Colors.ENDC}")

            # Create Kubernetes Secret for database credentials
            try:
                # Check if secret already exists and delete it
                subprocess.run(
                    ['kubectl', 'delete', 'secret', 'n8n-db-credentials', '-n', namespace],
                    capture_output=True
                )

                # Create new secret with database credentials
                result = subprocess.run([
                    'kubectl', 'create', 'secret', 'generic', 'n8n-db-credentials',
                    '-n', namespace,
                    f'--from-literal=password={db_config.get("rds_password", "")}'
                ], capture_output=True, text=True)

                if result.returncode != 0:
                    print(f"{Colors.FAIL}✗ Failed to create database credentials secret{Colors.ENDC}")
                    print(result.stderr)
                    return False

                print(f"{Colors.OKGREEN}  ✓ Database credentials stored securely in Kubernetes Secret{Colors.ENDC}")
            except Exception as e:
                print(f"{Colors.FAIL}✗ Error creating database secret: {e}{Colors.ENDC}")
                return False

            values_args.extend([
                '--set', 'database.type=postgresql',
                '--set', f'database.postgresql.host={db_config.get("rds_address", "")}',
                '--set', f'database.postgresql.port=5432',
                '--set', f'database.postgresql.database={db_config.get("rds_database_name", "n8n")}',
                '--set', f'database.postgresql.user={db_config.get("rds_username", "")}',
                # Password will be read from secret, not passed here
            ])
        else:
            # Default to SQLite
            values_args.extend([
                '--set', 'database.type=sqlite',
            ])

        success, output = self.run_command(values_args)

        if success:
            print(f"{Colors.OKGREEN}✓ n8n deployed successfully{Colors.ENDC}")
            if db_config and db_config.get('database_type') == 'postgresql':
                print(f"{Colors.OKGREEN}  Using PostgreSQL database at {db_config.get('rds_address')}{Colors.ENDC}")
            else:
                print(f"{Colors.OKGREEN}  Using SQLite database (file-based){Colors.ENDC}")

            # Wait for deployment to be ready
            print(f"\n{Colors.HEADER}Waiting for n8n deployment to be ready...{Colors.ENDC}")
            try:
                result = subprocess.run([
                    'kubectl', 'wait', '--for=condition=available',
                    '--timeout=300s',
                    'deployment/n8n',
                    '-n', namespace
                ], capture_output=True, text=True, timeout=310)

                if result.returncode == 0:
                    print(f"{Colors.OKGREEN}✓ n8n deployment is ready and available{Colors.ENDC}")
                else:
                    print(f"{Colors.WARNING}⚠ Deployment may not be fully ready yet{Colors.ENDC}")
                    print(f"{Colors.WARNING}  Check status with: kubectl get pods -n {namespace}{Colors.ENDC}")
            except subprocess.TimeoutExpired:
                print(f"{Colors.WARNING}⚠ Timeout waiting for deployment readiness{Colors.ENDC}")
                print(f"{Colors.WARNING}  Check status with: kubectl get pods -n {namespace}{Colors.ENDC}")
            except Exception as e:
                print(f"{Colors.WARNING}⚠ Could not verify deployment readiness: {e}{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}✗ n8n deployment failed{Colors.ENDC}")
            print(output)

        return success

    def upgrade_n8n_with_tls(self, config: DeploymentConfig, encryption_key: str, namespace: str = "n8n",
                             cert_manager_annotation: str = None) -> bool:
        """Upgrade n8n Helm release to enable TLS"""
        print(f"\n{Colors.HEADER}🔒 Upgrading n8n with TLS enabled...{Colors.ENDC}")

        values_args = [
            'upgrade', 'n8n', str(self.helm_dir),
            '--namespace', namespace,
            '--reuse-values',
            '--set', 'ingress.tls.enabled=true',
            '--set', f'env.N8N_PROTOCOL=https',
        ]

        # Add cert-manager annotation if using Let's Encrypt
        if cert_manager_annotation:
            values_args.extend([
                '--set', f'ingress.annotations.cert-manager\\.io/cluster-issuer={cert_manager_annotation}'
            ])

        success, output = self.run_command(values_args)

        if success:
            print(f"{Colors.OKGREEN}✓ n8n upgraded with TLS{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}✗ n8n TLS upgrade failed{Colors.ENDC}")
            print(output)

        return success

def get_loadbalancer_url(max_attempts: int = 30, delay: int = 10) -> Optional[str]:
    """Get the LoadBalancer URL from NGINX ingress controller

    Args:
        max_attempts: Maximum number of attempts to get the URL
        delay: Delay in seconds between attempts

    Returns:
        LoadBalancer DNS name or None if not found
    """
    print(f"\n{Colors.HEADER}⏳ Waiting for LoadBalancer to be ready...{Colors.ENDC}")

    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                ['kubectl', 'get', 'svc', '-n', 'ingress-nginx', 'ingress-nginx-controller',
                 '-o', 'jsonpath={.status.loadBalancer.ingress[0].hostname}'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                lb_url = result.stdout.strip()
                print(f"{Colors.OKGREEN}✓ LoadBalancer ready: {lb_url}{Colors.ENDC}")
                return lb_url

            print(f"  Attempt {attempt}/{max_attempts} - LoadBalancer not ready yet...")
            if attempt < max_attempts:
                import time
                time.sleep(delay)

        except Exception as e:
            print(f"{Colors.WARNING}Error checking LoadBalancer: {e}{Colors.ENDC}")
            if attempt < max_attempts:
                import time
                time.sleep(delay)

    print(f"{Colors.FAIL}✗ LoadBalancer not ready after {max_attempts * delay} seconds{Colors.ENDC}")
    return None

def configure_tls_interactive(config: DeploymentConfig, script_dir: Path, loadbalancer_url: str, namespace: str = "n8n") -> bool:
    """Interactive TLS configuration after deployment

    Args:
        config: Deployment configuration
        script_dir: Script directory path
        loadbalancer_url: LoadBalancer DNS name
        namespace: Kubernetes namespace for n8n

    Returns:
        True if TLS was configured successfully
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}TLS/HTTPS Configuration{Colors.ENDC}")
    print("=" * 60)
    print("Your n8n is currently accessible via HTTP (unencrypted)")
    print(f"LoadBalancer URL: {Colors.OKCYAN}{loadbalancer_url}{Colors.ENDC}")
    print()

    prompt = ConfigurationPrompt()

    if not prompt.prompt_yes_no("Would you like to configure TLS/HTTPS now?", default=False):
        print(f"\n{Colors.WARNING}TLS configuration skipped{Colors.ENDC}")
        print("You can configure TLS later by running:")
        print(f"  {Colors.OKCYAN}python3 setup.py --configure-tls{Colors.ENDC}")
        return False

    # TLS Configuration prompts
    print(f"\n{Colors.BOLD}Choose TLS certificate option:{Colors.ENDC}")

    tls_choice = prompt.prompt_choice(
        "TLS Configuration",
        [
            "Bring Your Own Certificate (provide PEM files)",
            "Let's Encrypt (auto-generated, HTTP-01 validation)"
        ],
        default=1
    )

    if "Bring Your Own" in tls_choice:
        config.tls_certificate_source = "byo"

        # Get certificate file
        while True:
            cert_path = prompt.prompt(
                "Path to TLS certificate file (PEM format)",
                required=True
            )
            valid, content = CertificateValidator.validate_pem_file(cert_path, "certificate")
            if valid:
                config.tls_certificate_crt = content
                print(f"{Colors.OKGREEN}✓ Certificate validated{Colors.ENDC}")
                break
            else:
                print(f"{Colors.FAIL}✗ {content}{Colors.ENDC}")

        # Get private key file
        while True:
            key_path = prompt.prompt(
                "Path to TLS private key file (PEM format)",
                required=True
            )
            valid, content = CertificateValidator.validate_pem_file(key_path, "key")
            if valid:
                config.tls_certificate_key = content
                print(f"{Colors.OKGREEN}✓ Private key validated{Colors.ENDC}")
                break
            else:
                print(f"{Colors.FAIL}✗ {content}{Colors.ENDC}")

        # Create TLS secret
        print(f"\n{Colors.HEADER}Creating TLS secret...{Colors.ENDC}")
        try:
            # Create temporary files for cert and key
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False) as cert_file:
                cert_file.write(config.tls_certificate_crt)
                cert_path = cert_file.name

            with tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as key_file:
                key_file.write(config.tls_certificate_key)
                key_path = key_file.name

            result = subprocess.run([
                'kubectl', 'create', 'secret', 'tls', 'n8n-tls',
                '-n', namespace,
                f'--cert={cert_path}',
                f'--key={key_path}'
            ], capture_output=True, text=True)

            # Clean up temp files
            os.unlink(cert_path)
            os.unlink(key_path)

            if result.returncode == 0:
                print(f"{Colors.OKGREEN}✓ TLS secret created{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}✗ Failed to create TLS secret{Colors.ENDC}")
                print(result.stderr)
                return False

        except Exception as e:
            print(f"{Colors.FAIL}✗ Error creating TLS secret: {e}{Colors.ENDC}")
            return False

    elif "Let's Encrypt" in tls_choice:
        config.tls_certificate_source = "letsencrypt"

        # Get email for Let's Encrypt
        while True:
            email = prompt.prompt(
                "Email address for Let's Encrypt notifications",
                required=True
            )
            if CertificateValidator.validate_email(email):
                config.letsencrypt_email = email
                print(f"{Colors.OKGREEN}✓ Email validated{Colors.ENDC}")
                break
            else:
                print(f"{Colors.FAIL}✗ Invalid email format{Colors.ENDC}")

        # Ask about staging vs production
        use_staging = prompt.prompt_yes_no(
            "Use Let's Encrypt staging environment? (recommended for testing)",
            default=False
        )
        config.letsencrypt_environment = "staging" if use_staging else "production"

        # Show DNS configuration instructions
        print(f"\n{Colors.WARNING}{Colors.BOLD}⚠️  IMPORTANT - DNS Configuration Required{Colors.ENDC}")
        print("=" * 60)
        print(f"Before proceeding, you MUST configure DNS:")
        print(f"\n1. Create a DNS record for: {Colors.OKCYAN}{config.n8n_host}{Colors.ENDC}")
        print(f"2. Point it to LoadBalancer: {Colors.OKCYAN}{loadbalancer_url}{Colors.ENDC}")
        print(f"\n   Record Type: {Colors.BOLD}CNAME{Colors.ENDC}")
        print(f"   Name: {Colors.OKCYAN}{config.n8n_host}{Colors.ENDC}")
        print(f"   Value: {Colors.OKCYAN}{loadbalancer_url}{Colors.ENDC}")
        print(f"\n   OR use an {Colors.BOLD}A record (ALIAS){Colors.ENDC} if your DNS provider supports it")
        print("=" * 60)

        if not prompt.prompt_yes_no("\nHave you configured the DNS record?", default=False):
            print(f"\n{Colors.WARNING}TLS configuration cancelled{Colors.ENDC}")
            print("Configure DNS and run setup with --configure-tls when ready")
            return False

        # Install cert-manager
        print(f"\n{Colors.HEADER}Installing cert-manager...{Colors.ENDC}")
        try:
            result = subprocess.run([
                'helm', 'install', 'cert-manager', 'https://charts.jetstack.io/charts/cert-manager-v1.13.3.tgz',
                '--namespace', 'cert-manager',
                '--create-namespace',
                '--set', 'installCRDs=true'
            ], capture_output=True, text=True, timeout=180)

            if result.returncode == 0:
                print(f"{Colors.OKGREEN}✓ cert-manager installed{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}✗ cert-manager installation failed{Colors.ENDC}")
                print(result.stderr)
                return False

        except Exception as e:
            print(f"{Colors.FAIL}✗ Error installing cert-manager: {e}{Colors.ENDC}")
            return False

        # Create ClusterIssuer
        print(f"\n{Colors.HEADER}Creating Let's Encrypt ClusterIssuer...{Colors.ENDC}")
        issuer_name = f"letsencrypt-{config.letsencrypt_environment}"
        issuer_yaml = f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {issuer_name}
spec:
  acme:
    server: {"https://acme-v02.api.letsencrypt.org/directory" if config.letsencrypt_environment == "production" else "https://acme-staging-v02.api.letsencrypt.org/directory"}
    email: {config.letsencrypt_email}
    privateKeySecretRef:
      name: {issuer_name}
    solvers:
    - http01:
        ingress:
          class: nginx
"""

        try:
            result = subprocess.run(
                ['kubectl', 'apply', '-f', '-'],
                input=issuer_yaml,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"{Colors.OKGREEN}✓ ClusterIssuer created{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}✗ Failed to create ClusterIssuer{Colors.ENDC}")
                print(result.stderr)
                return False

        except Exception as e:
            print(f"{Colors.FAIL}✗ Error creating ClusterIssuer: {e}{Colors.ENDC}")
            return False

    # Upgrade n8n with TLS
    helm_runner = HelmRunner(script_dir / "helm")

    # Get encryption key from outputs
    tf_runner = TerraformRunner(script_dir / "terraform")
    outputs = tf_runner.get_outputs()
    encryption_key = outputs.get('n8n_encryption_key_value', '')

    cert_manager_annotation = None
    if config.tls_certificate_source == "letsencrypt":
        cert_manager_annotation = f"letsencrypt-{config.letsencrypt_environment}"

    if helm_runner.upgrade_n8n_with_tls(config, encryption_key, namespace, cert_manager_annotation):
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ TLS Configuration Complete!{Colors.ENDC}")

        if config.tls_certificate_source == "letsencrypt":
            print("\n" + "=" * 60)
            print(f"{Colors.BOLD}Let's Encrypt Certificate Issuance{Colors.ENDC}")
            print("=" * 60)
            print("Certificate issuance typically takes 2-5 minutes")
            print("\nMonitor certificate status:")
            print(f"  {Colors.OKCYAN}kubectl get certificate -n {namespace}{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}kubectl describe certificate n8n-tls -n {namespace}{Colors.ENDC}")
            print("\nOnce ready, access n8n at:")
            print(f"  {Colors.OKGREEN}https://{config.n8n_host}{Colors.ENDC}")
            print("=" * 60)
        else:
            print(f"\nAccess n8n at: {Colors.OKGREEN}https://{config.n8n_host}{Colors.ENDC}")

        return True
    else:
        print(f"\n{Colors.FAIL}TLS configuration failed{Colors.ENDC}")
        return False

def configure_basic_auth_interactive(config: DeploymentConfig, script_dir: Path, namespace: str = "n8n") -> bool:
    """Interactive basic authentication configuration after deployment

    Args:
        config: Deployment configuration
        script_dir: Script directory path

    Returns:
        True if basic auth was configured successfully
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}Basic Authentication Configuration{Colors.ENDC}")
    print("=" * 60)
    print("Protect your n8n instance with basic authentication")
    print()

    prompt = ConfigurationPrompt()

    if not prompt.prompt_yes_no("Would you like to enable basic authentication?", default=False):
        print(f"\n{Colors.WARNING}Basic authentication skipped{Colors.ENDC}")
        print("Your n8n instance will be publicly accessible")
        return False

    # Generate credentials
    config.basic_auth_username = "admin"
    config.basic_auth_password = secrets.token_urlsafe(12)[:12]  # 12 character random password

    print(f"\n{Colors.OKGREEN}✓ Generated basic auth credentials{Colors.ENDC}")
    print(f"\n{Colors.WARNING}{Colors.BOLD}⚠️  IMPORTANT - Save these credentials!{Colors.ENDC}")
    print("=" * 60)
    print(f"Username: {Colors.OKCYAN}{config.basic_auth_username}{Colors.ENDC}")
    print(f"Password: {Colors.OKCYAN}{config.basic_auth_password}{Colors.ENDC}")
    print("=" * 60)
    print(f"{Colors.WARNING}These credentials will be required to access n8n{Colors.ENDC}")
    print()

    if not prompt.prompt_yes_no("Have you saved the credentials?", default=False):
        print(f"\n{Colors.FAIL}Please save the credentials before continuing{Colors.ENDC}")
        return False

    # Store credentials in AWS Secrets Manager
    print(f"\n{Colors.HEADER}Storing credentials in AWS Secrets Manager...{Colors.ENDC}")
    try:
        import boto3
        import botocore

        session = boto3.Session(profile_name=config.aws_profile, region_name=config.aws_region)
        secrets_client = session.client('secretsmanager')

        secret_value = json.dumps({
            'username': config.basic_auth_username,
            'password': config.basic_auth_password
        })

        try:
            # Try to create the secret
            secrets_client.create_secret(
                Name='/n8n/basic-auth',
                SecretString=secret_value,
                Description='Basic authentication credentials for n8n ingress'
            )
            print(f"{Colors.OKGREEN}✓ Credentials stored in AWS Secrets Manager{Colors.ENDC}")
        except secrets_client.exceptions.ResourceExistsException:
            # Secret already exists, update it
            secrets_client.put_secret_value(
                SecretId='/n8n/basic-auth',
                SecretString=secret_value
            )
            print(f"{Colors.OKGREEN}✓ Credentials updated in AWS Secrets Manager{Colors.ENDC}")

    except Exception as e:
        print(f"{Colors.FAIL}✗ Failed to store credentials in Secrets Manager: {e}{Colors.ENDC}")
        print(f"{Colors.WARNING}Continuing with local credential storage only{Colors.ENDC}")

    # Create htpasswd file content with bcrypt
    print(f"\n{Colors.HEADER}Creating basic auth secret in Kubernetes...{Colors.ENDC}")
    try:
        # Try using htpasswd command (required for bcrypt)
        try:
            result = subprocess.run(
                ['htpasswd', '-nB', config.basic_auth_username],
                input=f"{config.basic_auth_password}\n{config.basic_auth_password}\n",
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                auth_content = result.stdout.strip()
            else:
                raise Exception(f"htpasswd command failed: {result.stderr}")

        except FileNotFoundError:
            print(f"{Colors.FAIL}✗ htpasswd command not found{Colors.ENDC}")
            print(f"\n{Colors.WARNING}Basic authentication requires htpasswd for bcrypt hashing.{Colors.ENDC}")
            print(f"\nInstall apache2-utils (Debian/Ubuntu) or httpd-tools (RedHat/CentOS):")
            print(f"  {Colors.OKCYAN}# Ubuntu/Debian:{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}sudo apt-get install apache2-utils{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}# RedHat/CentOS:{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}sudo yum install httpd-tools{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}# macOS:{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}brew install httpd{Colors.ENDC}")
            return False
        except subprocess.TimeoutExpired:
            print(f"{Colors.FAIL}✗ htpasswd command timed out{Colors.ENDC}")
            return False

        # Create Kubernetes secret
        result = subprocess.run([
            'kubectl', 'create', 'secret', 'generic', 'n8n-basic-auth',
            '-n', namespace,
            f'--from-literal=auth={auth_content}'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print(f"{Colors.OKGREEN}✓ Basic auth secret created in Kubernetes{Colors.ENDC}")
        else:
            # Secret might already exist, try to delete and recreate
            subprocess.run(['kubectl', 'delete', 'secret', 'n8n-basic-auth', '-n', namespace],
                         capture_output=True)
            result = subprocess.run([
                'kubectl', 'create', 'secret', 'generic', 'n8n-basic-auth',
                '-n', namespace,
                f'--from-literal=auth={auth_content}'
            ], capture_output=True, text=True)

            if result.returncode == 0:
                print(f"{Colors.OKGREEN}✓ Basic auth secret created in Kubernetes{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}✗ Failed to create basic auth secret{Colors.ENDC}")
                print(result.stderr)
                return False

    except Exception as e:
        print(f"{Colors.FAIL}✗ Error creating basic auth secret: {e}{Colors.ENDC}")
        return False

    # Upgrade n8n Helm release with basic auth enabled
    print(f"\n{Colors.HEADER}Enabling basic auth in n8n ingress...{Colors.ENDC}")
    try:
        result = subprocess.run([
            'helm', 'upgrade', 'n8n', str(script_dir / 'helm'),
            '-n', namespace,
            '--reuse-values',
            '--set', 'ingress.basicAuth.enabled=true',
            '--set', 'ingress.basicAuth.secretName=n8n-basic-auth'
        ], capture_output=True, text=True, timeout=180)

        if result.returncode == 0:
            print(f"{Colors.OKGREEN}✓ Basic auth enabled on n8n ingress{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}✗ Failed to enable basic auth{Colors.ENDC}")
            print(result.stderr)
            return False

    except Exception as e:
        print(f"{Colors.FAIL}✗ Error enabling basic auth: {e}{Colors.ENDC}")
        return False

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ Basic Authentication Configured!{Colors.ENDC}")
    print("\n" + "=" * 60)
    print(f"Basic auth is now required to access n8n")
    print(f"Username: {Colors.OKCYAN}{config.basic_auth_username}{Colors.ENDC}")
    print(f"Password: {Colors.OKCYAN}{config.basic_auth_password}{Colors.ENDC}")
    print("=" * 60)

    return True

def main():
    """Main execution flow for N8N EKS deployment - 4 Phase Deployment"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='N8N EKS Deployment Setup')
    parser.add_argument('--configure-tls', action='store_true',
                       help='Configure TLS for existing n8n deployment')
    args = parser.parse_args()

    script_dir = Path(__file__).parent

    print(f"{Colors.BOLD}{Colors.HEADER}")
    print("=" * 60)
    print("  N8N EKS Deployment Setup")
    print("=" * 60)
    print(Colors.ENDC)

    try:
        # Check dependencies
        deps_ok, missing = DependencyChecker.check_all_dependencies()
        if not deps_ok:
            sys.exit(1)

        if args.configure_tls:
            try:
                config = load_existing_configuration(script_dir)
            except Exception as e:
                print(f"{Colors.FAIL}✗ Unable to load existing configuration: {e}{Colors.ENDC}")
                print("Run the full deployment once before using --configure-tls.")
                sys.exit(1)

            loadbalancer_url = get_loadbalancer_url(max_attempts=30, delay=10)
            if not loadbalancer_url:
                print(f"{Colors.FAIL}✗ Unable to determine LoadBalancer hostname{Colors.ENDC}")
                print("Ensure kubectl is pointed at your cluster and try again.")
                sys.exit(1)

            success = configure_tls_interactive(config, script_dir, loadbalancer_url)
            sys.exit(0 if success else 1)

        # Collect configuration (skip TLS - will be configured after LoadBalancer is ready)
        print(f"\n{Colors.HEADER}Let's configure your EKS deployment...{Colors.ENDC}")
        prompt = ConfigurationPrompt()
        config = prompt.collect_configuration(skip_tls=True)

        # Update configuration files
        updater = FileUpdater(script_dir)
        updater.apply_configuration(config)

        # ═══════════════════════════════════════════════════════════════
        # PHASE 1: Deploy Infrastructure (Terraform)
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.HEADER}{Colors.BOLD}📦 PHASE 1: Deploying Infrastructure{Colors.ENDC}")
        print("=" * 60)
        print("This will create:")
        print("  • VPC, subnets, NAT gateways (~5 minutes)")
        print("  • EKS cluster and node group (~15-20 minutes)")
        print("  • NGINX ingress controller with LoadBalancer (~2 minutes)")
        print("  • EBS CSI driver and StorageClass")
        print(f"\n{Colors.WARNING}⏱  Estimated time: ~22-27 minutes{Colors.ENDC}\n")

        tf_runner = TerraformRunner(script_dir / "terraform")

        if not tf_runner.init():
            raise Exception("Terraform initialization failed")

        # Run plan and display summary
        plan_success, plan_output = tf_runner.plan(display_output=True)
        if not plan_success:
            raise Exception("Terraform plan failed")

        # Ask user to confirm before applying
        prompt = ConfigurationPrompt()
        if not prompt.prompt_yes_no("\nProceed with Terraform apply?", default=True):
            raise SetupInterrupted("User cancelled Terraform apply")

        if not tf_runner.apply():
            raise Exception("Terraform apply failed")

        print(f"\n{Colors.OKGREEN}✓ Infrastructure deployed successfully{Colors.ENDC}")

        # Get outputs
        outputs = tf_runner.get_outputs()

        # Configure kubectl
        if 'configure_kubectl' in outputs:
            print(f"\n{Colors.HEADER}🔧 Configuring kubectl...{Colors.ENDC}")
            kubectl_cmd = outputs['configure_kubectl']
            result = subprocess.run(kubectl_cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"{Colors.OKGREEN}✓ kubectl configured{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}⚠  kubectl configuration failed. Run manually:{Colors.ENDC}")
                print(f"  {Colors.OKCYAN}{kubectl_cmd}{Colors.ENDC}")
                raise Exception("kubectl configuration required")

        # ═══════════════════════════════════════════════════════════════
        # PHASE 2: Deploy n8n Application (Helm)
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.HEADER}{Colors.BOLD}🚀 PHASE 2: Deploying n8n Application{Colors.ENDC}")
        print("=" * 60)

        helm_runner = HelmRunner(script_dir / "helm")
        encryption_key = outputs.get('n8n_encryption_key_value', '')

        if not encryption_key:
            raise Exception("Failed to retrieve encryption key from Terraform outputs")

        # Prepare database configuration from Terraform outputs
        db_config = {
            'database_type': outputs.get('database_type', 'sqlite'),
            'rds_address': outputs.get('rds_address'),
            'rds_port': outputs.get('rds_port'),
            'rds_database_name': outputs.get('rds_database_name'),
            'rds_username': outputs.get('rds_username'),
            'rds_password': outputs.get('rds_password'),
        }

        # Deploy n8n without TLS initially (but with database configuration)
        if not helm_runner.deploy_n8n(config, encryption_key, namespace="n8n", tls_enabled=False, db_config=db_config):
            raise Exception("n8n deployment failed")

        print(f"\n{Colors.OKGREEN}✓ n8n application deployed{Colors.ENDC}")

        # ═══════════════════════════════════════════════════════════════
        # PHASE 3: Get LoadBalancer URL
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.HEADER}{Colors.BOLD}🌐 PHASE 3: Retrieving LoadBalancer URL{Colors.ENDC}")
        print("=" * 60)

        loadbalancer_url = get_loadbalancer_url(max_attempts=30, delay=10)

        if not loadbalancer_url:
            print(f"\n{Colors.WARNING}⚠  LoadBalancer URL not available yet{Colors.ENDC}")
            print("Try retrieving it manually with:")
            print(f"  {Colors.OKCYAN}kubectl get svc -n ingress-nginx ingress-nginx-controller{Colors.ENDC}")
            loadbalancer_url = "<pending>"

        # ═══════════════════════════════════════════════════════════════
        # DEPLOYMENT COMPLETE - Show Access Information
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
        print(f"{Colors.OKGREEN}{Colors.BOLD}  🎉 N8N DEPLOYMENT COMPLETE!{Colors.ENDC}")
        print(f"{Colors.OKGREEN}{Colors.BOLD}{'=' * 60}{Colors.ENDC}\n")

        print(f"{Colors.BOLD}Your n8n instance is now running!{Colors.ENDC}\n")
        print(f"LoadBalancer URL: {Colors.OKCYAN}{loadbalancer_url}{Colors.ENDC}")
        print(f"Access n8n at:    {Colors.OKCYAN}http://{loadbalancer_url}{Colors.ENDC}")
        print(f"\n{Colors.WARNING}⚠  Currently using HTTP (unencrypted){Colors.ENDC}\n")

        # ═══════════════════════════════════════════════════════════════
        # PHASE 4: TLS and Basic Auth Configuration (Optional)
        # ═══════════════════════════════════════════════════════════════
        if loadbalancer_url != "<pending>":
            # Configure TLS first
            configure_tls_interactive(config, script_dir, loadbalancer_url, config.n8n_namespace)

            # Then configure Basic Auth
            configure_basic_auth_interactive(config, script_dir, config.n8n_namespace)

        # Show useful kubectl commands
        print(f"\n{Colors.BOLD}Useful Commands:{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl get pods -n {config.n8n_namespace}{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl get ingress -n {config.n8n_namespace}{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl logs -f deployment/n8n -n {config.n8n_namespace}{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl get svc -n ingress-nginx{Colors.ENDC}")

        if config.tls_certificate_source in ["byo", "letsencrypt"]:
            print(f"  {Colors.OKCYAN}kubectl get certificate -n {config.n8n_namespace}{Colors.ENDC}")

        print("\n" + "=" * 60)

        # Cleanup backup on success
        updater.cleanup_backup()

    except SetupInterrupted as e:
        print(f"\n{Colors.WARNING}{e}{Colors.ENDC}")
        if 'updater' in locals():
            updater.restore_backup()
            updater.cleanup_backup()
        sys.exit(1)

    except Exception as e:
        print(f"\n{Colors.FAIL}Error: {e}{Colors.ENDC}")
        if 'updater' in locals():
            updater.restore_backup()
            updater.cleanup_backup()
        sys.exit(1)

if __name__ == "__main__":
    main()
