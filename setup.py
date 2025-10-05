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
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
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
        self.n8n_host: str = ""
        self.timezone: str = "America/Bahia"
        self.n8n_encryption_key: str = ""

        # TLS Configuration
        self.tls_certificate_source: str = "none"  # "none", "byo", or "letsencrypt"
        self.tls_certificate_crt: str = ""  # PEM content for BYO
        self.tls_certificate_key: str = ""  # PEM content for BYO
        self.letsencrypt_email: str = ""
        self.letsencrypt_environment: str = "production"  # "staging" or "production"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'aws_profile': self.aws_profile,
            'aws_region': self.aws_region,
            'cluster_name': self.cluster_name,
            'node_instance_types': self.node_instance_types,
            'node_desired_size': self.node_desired_size,
            'n8n_host': self.n8n_host,
            'timezone': self.timezone,
            'tls_certificate_source': self.tls_certificate_source,
            'letsencrypt_email': self.letsencrypt_email,
            'letsencrypt_environment': self.letsencrypt_environment,
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
    def check_tool(tool_name: str) -> bool:
        """Check if a tool is installed"""
        return shutil.which(tool_name) is not None

    @classmethod
    def check_all_dependencies(cls) -> Tuple[bool, list]:
        """Check all required dependencies for EKS deployment"""
        missing = []

        print(f"\n{Colors.HEADER}🔍 Checking dependencies for EKS deployment...{Colors.ENDC}")

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

        # N8N Configuration
        print(f"\n{Colors.BOLD}N8N Configuration{Colors.ENDC}")

        self.config.n8n_host = self.prompt(
            "N8N Hostname (FQDN for ingress)",
            default="n8n.example.com",
            required=True
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
        print(f"Node Count:      {Colors.OKCYAN}{self.config.node_desired_size}{Colors.ENDC}")
        print(f"N8N Host:        {Colors.OKCYAN}{self.config.n8n_host}{Colors.ENDC}")
        print(f"Timezone:        {Colors.OKCYAN}{self.config.timezone}{Colors.ENDC}")
        print(f"Encryption Key:  {Colors.OKCYAN}{'*' * 20} (hidden){Colors.ENDC}")
        print("=" * 60)
        print(f"\n{Colors.WARNING}Note: TLS will be configured after deployment{Colors.ENDC}")

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
            f'n8n_host           = "{config.n8n_host}"',
            f'timezone           = "{config.timezone}"',
            f'n8n_encryption_key = "{config.n8n_encryption_key}"',
            f'n8n_namespace      = "n8n"',
            "",
        ]

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

    def plan(self) -> bool:
        """Run Terraform plan"""
        print(f"\n{Colors.HEADER}📋 Running Terraform plan...{Colors.ENDC}")
        success, output = self.run_command(['plan'])

        if success:
            print(f"{Colors.OKGREEN}✓ Terraform plan completed{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}✗ Terraform plan failed{Colors.ENDC}")
            print(output)

        return success

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

    def run_command(self, args: list) -> Tuple[bool, str]:
        """Run a helm command"""
        cmd = ['helm'] + args

        try:
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

    def install(self, release_name: str = "n8n", namespace: str = "default") -> bool:
        """Install Helm chart"""
        print(f"\n{Colors.HEADER}🎯 Installing Helm chart...{Colors.ENDC}")

        success, output = self.run_command([
            'install', release_name, str(self.helm_dir),
            '--namespace', namespace,
            '--create-namespace'
        ])

        if success:
            print(f"{Colors.OKGREEN}✓ Helm chart installed{Colors.ENDC}")
            print(output)
        else:
            print(f"{Colors.FAIL}✗ Helm install failed{Colors.ENDC}")
            print(output)

        return success

def main():
    """Main execution flow for N8N EKS deployment"""
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

        # Collect configuration
        print(f"\n{Colors.HEADER}Let's configure your EKS deployment...{Colors.ENDC}")
        prompt = ConfigurationPrompt()
        config = prompt.collect_configuration()

        # Update configuration files
        updater = FileUpdater(script_dir)
        updater.apply_configuration(config)

        # EKS deployment: Terraform handles everything (cluster + n8n via Helm)
        print(f"\n{Colors.HEADER}🚀 Starting EKS deployment...{Colors.ENDC}")
        print("This will:")
        print("  1. Create VPC, subnets, and networking (~5 minutes)")
        print("  2. Create EKS cluster and node group (~15-20 minutes)")
        print("  3. Deploy NGINX ingress controller (~2 minutes)")
        if config.tls_certificate_source == "letsencrypt":
            print("  4. Install cert-manager for Let's Encrypt (~2 minutes)")
            print("  5. Deploy n8n with automatic TLS certificate (~3 minutes)")
        else:
            print("  4. Deploy n8n via Helm (~2 minutes)")
        print(f"\n{Colors.WARNING}Total estimated time: ~25-30 minutes{Colors.ENDC}")

        tf_runner = TerraformRunner(script_dir / "terraform")

        if not tf_runner.init():
            raise Exception("Terraform initialization failed")

        if not tf_runner.plan():
            raise Exception("Terraform plan failed")

        if not tf_runner.apply():
            raise Exception("Terraform apply failed")

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
                print(f"{Colors.WARNING}⚠ kubectl configuration failed. Run manually:{Colors.ENDC}")
                print(f"  {Colors.OKCYAN}{kubectl_cmd}{Colors.ENDC}")

        # Display success and access instructions
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}🎉 EKS Deployment Complete!{Colors.ENDC}")
        print("=" * 60)

        # Show access instructions from Terraform output
        if 'access_instructions' in outputs:
            print(f"\n{outputs['access_instructions']}")

        # Show useful kubectl commands
        n8n_namespace = outputs.get('n8n_namespace', 'n8n')
        print(f"\n{Colors.BOLD}Useful Commands:{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl get pods -n {n8n_namespace}{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl get ingress -n {n8n_namespace}{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl get svc -n ingress-nginx{Colors.ENDC}")
        if config.tls_certificate_source == "letsencrypt":
            print(f"  {Colors.OKCYAN}kubectl get certificate -n {n8n_namespace}{Colors.ENDC}")

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
