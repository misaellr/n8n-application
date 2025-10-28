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
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import signal
from datetime import datetime

# ANSI color codes
class Colors:
    HEADER = '\033[94m'    # Light Blue for headers
    OKBLUE = '\033[1;94m'   # Bold Light Blue for branding elements
    OKCYAN = '\033[96m'    # Cyan for informational text
    OKGREEN = '\033[92m'   # Green for success messages
    WARNING = '\033[93m'   # Yellow for warnings
    FAIL = '\033[91m'      # Red for errors
    RED = '\033[91m'       # Red (alias for compatibility)
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class SetupInterrupted(Exception):
    """Raised when user interrupts the setup process"""
    pass

class ConfigHistoryManager:
    """Manages configuration history - saves every setup.py run for easy reference"""

    HISTORY_FILE = "setup_history.log"
    CURRENT_CONFIG_FILE = ".setup-current.json"

    @staticmethod
    def save_configuration(config: Any, cloud_provider: str, base_dir: Path):
        """Save configuration to history file (prepended) and current config file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Prepare configuration data
        if hasattr(config, 'to_dict'):
            config_dict = config.to_dict()
        else:
            config_dict = vars(config)

        # Save current configuration as JSON for easy re-loading
        current_file = base_dir / ConfigHistoryManager.CURRENT_CONFIG_FILE
        try:
            with open(current_file, 'w') as f:
                json.dump({
                    'timestamp': timestamp,
                    'cloud_provider': cloud_provider,
                    'configuration': config_dict
                }, f, indent=2)
        except Exception as e:
            print(f"{Colors.WARNING}⚠ Warning: Could not save current config: {e}{Colors.ENDC}")

        # Prepare history entry
        history_entry = ConfigHistoryManager._format_history_entry(
            timestamp, cloud_provider, config_dict
        )

        # Prepend to history file
        history_file = base_dir / ConfigHistoryManager.HISTORY_FILE
        try:
            # Read existing content if file exists
            existing_content = ""
            if history_file.exists():
                existing_content = history_file.read_text()

            # Write new entry at the top
            with open(history_file, 'w') as f:
                f.write(history_entry)
                f.write("\n" + "=" * 80 + "\n\n")
                if existing_content:
                    f.write(existing_content)

            print(f"{Colors.OKGREEN}✓ Configuration saved to {ConfigHistoryManager.HISTORY_FILE}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}⚠ Warning: Could not save config history: {e}{Colors.ENDC}")

    @staticmethod
    def _format_history_entry(timestamp: str, cloud_provider: str, config_dict: Dict) -> str:
        """Format a configuration as a readable markdown entry"""
        lines = [
            f"# Configuration - {timestamp}",
            f"",
            f"**Cloud Provider:** {cloud_provider.upper()}",
            f"**Timestamp:** {timestamp}",
            f"",
            f"## Configuration Parameters",
            f""
        ]

        # Group configuration by category
        categories = {
            'Cloud & Infrastructure': ['cloud_provider', 'aws_region', 'aws_profile', 'azure_subscription_id', 'azure_location', 'resource_group_name', 'gcp_project_id', 'gcp_region', 'gcp_zone', 'vpc_name', 'subnet_name'],
            'Cluster': ['cluster_name', 'kubernetes_version', 'node_vm_size', 'node_instance_types', 'node_count', 'node_desired_size', 'node_min_size', 'node_max_size', 'node_min_count', 'node_max_count', 'enable_auto_scaling', 'node_machine_type'],
            'Application': ['n8n_host', 'n8n_namespace', 'n8n_protocol', 'n8n_persistence_size', 'timezone', 'n8n_encryption_key'],
            'Database': ['database_type', 'rds_instance_class', 'rds_allocated_storage', 'rds_multi_az', 'postgres_sku', 'postgres_storage_gb', 'postgres_high_availability', 'cloudsql_instance_name', 'cloudsql_tier'],
            'Networking & Security': ['use_static_ip', 'enable_nginx_ingress', 'enable_basic_auth', 'basic_auth_username', 'enable_cert_manager', 'tls_certificate_source', 'letsencrypt_email', 'enable_tls', 'tls_provider'],
            'Permissions': ['terraform_manage_role_assignments']
        }

        for category, keys in categories.items():
            category_items = []
            for key in keys:
                if key in config_dict:
                    value = config_dict[key]
                    # Hide sensitive values
                    if key in ['n8n_encryption_key', 'basic_auth_password']:
                        value = "***REDACTED***"
                    elif value == "":
                        value = "(empty)"
                    category_items.append(f"- **{key}**: `{value}`")

            if category_items:
                lines.append(f"### {category}")
                lines.extend(category_items)
                lines.append("")

        # Add any remaining keys not in categories
        uncategorized = []
        all_categorized_keys = set(k for keys in categories.values() for k in keys)
        for key, value in config_dict.items():
            if key not in all_categorized_keys:
                if key in ['n8n_encryption_key', 'basic_auth_password']:
                    value = "***REDACTED***"
                elif value == "":
                    value = "(empty)"
                uncategorized.append(f"- **{key}**: `{value}`")

        if uncategorized:
            lines.append("### Other")
            lines.extend(uncategorized)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def load_previous_configuration(base_dir: Path) -> Optional[Dict]:
        """Load the most recent configuration from .setup-current.json"""
        current_file = base_dir / ConfigHistoryManager.CURRENT_CONFIG_FILE

        if not current_file.exists():
            return None

        try:
            with open(current_file, 'r') as f:
                data = json.load(f)
            return data
        except Exception as e:
            print(f"{Colors.WARNING}⚠ Warning: Could not load previous config: {e}{Colors.ENDC}")
            return None

class AWSDeploymentConfig:
    """Stores all configuration for AWS EKS deployment"""
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
        self.enable_nginx_ingress: bool = True

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
            'enable_nginx_ingress': self.enable_nginx_ingress,
            'tls_certificate_source': self.tls_certificate_source,
            'letsencrypt_email': self.letsencrypt_email,
            'letsencrypt_environment': self.letsencrypt_environment,
            'database_type': self.database_type,
            'rds_instance_class': self.rds_instance_class,
            'rds_allocated_storage': self.rds_allocated_storage,
            'rds_multi_az': self.rds_multi_az,
            'enable_basic_auth': self.enable_basic_auth,
        }

# Backward compatibility alias
DeploymentConfig = AWSDeploymentConfig

class AzureDeploymentConfig:
    """Stores all configuration for Azure AKS deployment"""
    def __init__(self):
        self.cloud_provider: str = "azure"
        self.azure_subscription_id: Optional[str] = None
        self.azure_location: str = "eastus"
        self.resource_group_name: str = "n8n-rg"
        self.cluster_name: str = "n8n-aks-cluster"
        self.kubernetes_version: str = "1.31.11"
        self.node_vm_size: str = "Standard_D2s_v3"
        self.node_count: int = 2
        self.node_min_count: int = 1
        self.node_max_count: int = 5
        self.enable_auto_scaling: bool = True

        # Application Configuration
        self.n8n_namespace: str = "n8n"
        self.n8n_host: str = ""
        self.n8n_protocol: str = "http"
        self.timezone: str = "America/Bahia"
        self.n8n_encryption_key: str = ""
        self.n8n_persistence_size: str = "10Gi"
        self.enable_nginx_ingress: bool = True
        self.use_static_ip: bool = False  # Use pre-allocated static IP
        self.terraform_manage_role_assignments: bool = True  # Let Terraform create role assignments (requires elevated permissions)

        # TLS Configuration
        self.tls_certificate_source: str = "none"  # "none", "byo", or "letsencrypt"
        self.tls_certificate_crt: str = ""
        self.tls_certificate_key: str = ""
        self.letsencrypt_email: str = ""
        self.enable_cert_manager: bool = False

        # Database Configuration
        self.database_type: str = "sqlite"  # "sqlite" or "postgresql"
        self.postgres_sku: str = "B_Standard_B1ms"
        self.postgres_storage_gb: int = 32
        self.postgres_high_availability: bool = False

        # Basic Authentication
        self.enable_basic_auth: bool = False
        self.basic_auth_username: str = "admin"
        self.basic_auth_password: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'cloud_provider': self.cloud_provider,
            'azure_subscription_id': self.azure_subscription_id,
            'azure_location': self.azure_location,
            'resource_group_name': self.resource_group_name,
            'cluster_name': self.cluster_name,
            'kubernetes_version': self.kubernetes_version,
            'node_vm_size': self.node_vm_size,
            'node_count': self.node_count,
            'node_min_count': self.node_min_count,
            'node_max_count': self.node_max_count,
            'enable_auto_scaling': self.enable_auto_scaling,
            'n8n_namespace': self.n8n_namespace,
            'n8n_host': self.n8n_host,
            'n8n_protocol': self.n8n_protocol,
            'timezone': self.timezone,
            'n8n_persistence_size': self.n8n_persistence_size,
            'enable_nginx_ingress': self.enable_nginx_ingress,
            'use_static_ip': self.use_static_ip,
            'terraform_manage_role_assignments': self.terraform_manage_role_assignments,
            'tls_certificate_source': self.tls_certificate_source,
            'letsencrypt_email': self.letsencrypt_email,
            'enable_cert_manager': self.enable_cert_manager,
            'database_type': self.database_type,
            'postgres_sku': self.postgres_sku,
            'postgres_storage_gb': self.postgres_storage_gb,
            'postgres_high_availability': self.postgres_high_availability,
            'enable_basic_auth': self.enable_basic_auth,
        }

class GCPDeploymentConfig:
    """Stores all configuration for GCP GKE deployment

    Maps to AWS/Azure equivalents:
    - gcp_project_id      → aws_profile / azure_subscription_id
    - gcp_region + zone   → aws_region / azure_location
    - cluster_name        → eks_cluster_name / cluster_name
    - node_machine_type   → node_instance_type / node_vm_size
    - database_type       → RDS / Azure PostgreSQL / Cloud SQL
    """
    def __init__(self):
        self.cloud_provider: str = "gcp"

        # GCP-specific settings
        self.gcp_project_id: str = ""
        self.gcp_region: str = "us-central1"
        self.gcp_zone: str = "us-central1-a"

        # Cluster settings
        self.cluster_name: str = "n8n-gke-cluster"
        self.node_machine_type: str = "e2-medium"
        self.node_count: int = 1

        # Network settings
        self.vpc_name: str = "n8n-vpc"
        self.subnet_name: str = "n8n-subnet"

        # Database settings (matches AWS/Azure pattern)
        self.database_type: str = "sqlite"  # "sqlite" or "cloudsql"
        self.cloudsql_instance_name: str = ""
        self.cloudsql_tier: str = "db-f1-micro"

        # Application settings
        self.n8n_namespace: str = "n8n"
        self.n8n_host: str = ""
        self.n8n_protocol: str = "http"
        self.n8n_encryption_key: str = ""

        # TLS settings (matches AWS/Azure pattern)
        self.enable_tls: bool = False
        self.tls_provider: str = "letsencrypt"  # "letsencrypt" or "custom"
        self.letsencrypt_email: str = ""

        # Basic auth settings (matches AWS/Azure pattern)
        self.enable_basic_auth: bool = False
        self.basic_auth_username: str = "admin"
        self.basic_auth_password: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration to dictionary for JSON export"""
        return {
            'cloud_provider': self.cloud_provider,
            'gcp_project_id': self.gcp_project_id,
            'gcp_region': self.gcp_region,
            'gcp_zone': self.gcp_zone,
            'cluster_name': self.cluster_name,
            'node_machine_type': self.node_machine_type,
            'node_count': self.node_count,
            'vpc_name': self.vpc_name,
            'subnet_name': self.subnet_name,
            'database_type': self.database_type,
            'cloudsql_instance_name': self.cloudsql_instance_name,
            'cloudsql_tier': self.cloudsql_tier,
            'n8n_namespace': self.n8n_namespace,
            'n8n_host': self.n8n_host,
            'n8n_protocol': self.n8n_protocol,
            'n8n_encryption_key': self.n8n_encryption_key,
            'enable_tls': self.enable_tls,
            'tls_provider': self.tls_provider,
            'letsencrypt_email': self.letsencrypt_email,
            'enable_basic_auth': self.enable_basic_auth,
            'basic_auth_username': self.basic_auth_username,
        }

class DependencyChecker:
    """Checks for required CLI tools for deployment"""

    COMMON_TOOLS = {
        'terraform': {
            'command': 'terraform version',
            'version_regex': r'Terraform v([0-9]+\.[0-9]+\.[0-9]+)',
            'min_version': '1.6.0',
            'install_url': 'https://developer.hashicorp.com/terraform/downloads',
            'description': 'Infrastructure as Code tool'
        },
        'helm': {
            'command': 'helm version',
            'version_regex': r'v([0-9]+\.[0-9]+\.[0-9]+)',
            'min_version': '3.0.0',
            'install_url': 'https://helm.sh/docs/intro/install/',
            'description': 'Kubernetes package manager'
        },
        'kubectl': {
            'command': 'kubectl version --client',
            'version_regex': r'Client Version: v([0-9]+\.[0-9]+\.[0-9]+)',
            'min_version': '1.20.0',
            'description': 'Kubernetes command-line tool',
            'install_url': 'https://kubernetes.io/docs/tasks/tools/',
        },
        'openssl': {
            'command': 'openssl version',
            'version_regex': r'OpenSSL ([0-9]+\.[0-9]+\.[0-9]+)',
            'min_version': '1.1.1',
            'description': 'Cryptography and SSL/TLS toolkit',
            'install_url': 'https://www.openssl.org/source/',
        }
    }

    AWS_TOOLS = {
        'aws': {
            'command': 'aws --version',
            'version_regex': r'aws-cli/([0-9]+\.[0-9]+\.[0-9]+)',
            'min_version': '2.0.0',
            'install_url': 'https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html',
            'description': 'AWS Command Line Interface'
        }
    }

    AZURE_TOOLS = {
        'az': {
            'command': 'az version',
            'version_regex': r'"azure-cli":\s*"([0-9]+\.[0-9]+\.[0-9]+)"',
            'min_version': '2.50.0',
            'install_url': 'https://learn.microsoft.com/en-us/cli/azure/install-azure-cli',
            'description': 'Azure Command Line Interface'
        }
    }

    GCP_TOOLS = {
        'gcloud': {
            'command': 'gcloud version',
            'version_regex': r'Google Cloud SDK ([0-9]+\.[0-9]+\.[0-9]+)',
            'min_version': '400.0.0',
            'install_url': 'https://cloud.google.com/sdk/docs/install',
            'description': 'Google Cloud Command Line Interface'
        }
    }

    # Backward compatibility
    REQUIRED_TOOLS = {**COMMON_TOOLS, **AWS_TOOLS}

    @staticmethod
    def check_python_version() -> Tuple[bool, str]:
        """Check if Python version is 3.7 or higher"""
        major, minor = sys.version_info[:2]
        current_version = f"{major}.{minor}"

        if major < 3 or (major == 3 and minor < 7):
            return False, f"Python {current_version} (requires 3.7+)"
        return True, f"Python {current_version}"

    @staticmethod
    def _compare_versions(version1: str, version2: str) -> int:
        """Compare two version strings (e.g., '1.6.0', '1.10.2').
        Returns:
            -1 if version1 < version2
             0 if version1 == version2
             1 if version1 > version2
        """
        v1_parts = [int(p) for p in version1.split('.')]
        v2_parts = [int(p) for p in version2.split('.')]
        for i in range(max(len(v1_parts), len(v2_parts))):
            v1_part = v1_parts[i] if i < len(v1_parts) else 0
            v2_part = v2_parts[i] if i < len(v2_parts) else 0
            if v1_part < v2_part:
                return -1
            if v1_part > v2_part:
                return 1
        return 0

    @classmethod
    def check_all_dependencies(cls, cloud_provider: str = "aws") -> Tuple[bool, list]:
        """Check all required dependencies for deployment

        Args:
            cloud_provider: Either "aws", "azure", or "gcp"
        """
        missing = []
        outdated = []
        import re

        provider_names = {
            "aws": "AWS EKS",
            "azure": "Azure AKS",
            "gcp": "GCP GKE"
        }
        provider_name = provider_names.get(cloud_provider, "AWS EKS")
        print(f"\n{Colors.HEADER}🔍 Checking dependencies for {provider_name} deployment...{Colors.ENDC}")

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

        # Select tools based on cloud provider
        if cloud_provider == "azure":
            required_tools = {**cls.COMMON_TOOLS, **cls.AZURE_TOOLS}
        elif cloud_provider == "gcp":
            required_tools = {**cls.COMMON_TOOLS, **cls.GCP_TOOLS}
        else:
            required_tools = {**cls.COMMON_TOOLS, **cls.AWS_TOOLS}

        # Check all required tools
        for tool, info in required_tools.items():
            if not shutil.which(tool):
                print(f"{Colors.FAIL}✗{Colors.ENDC} {tool} - NOT installed")
                missing.append((tool, info))
                continue

            try:
                result = subprocess.run(
                    info['command'].split(),
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                version_match = re.search(info['version_regex'], result.stdout)
                if not version_match:
                    version_match = re.search(info['version_regex'], result.stderr)

                if version_match:
                    installed_version = version_match.group(1)
                    min_version = info['min_version']
                    if cls._compare_versions(installed_version, min_version) >= 0:
                        print(f"{Colors.OKGREEN}✓{Colors.ENDC} {tool} - installed (v{installed_version})")
                    else:
                        print(f"{Colors.FAIL}✗{Colors.ENDC} {tool} - outdated (v{installed_version}, requires >={min_version})")
                        outdated.append((tool, info, installed_version))
                else:
                    print(f"{Colors.WARNING}✓{Colors.ENDC} {tool} - installed (could not determine version)")

            except Exception:
                print(f"{Colors.WARNING}✓{Colors.ENDC} {tool} - installed (could not verify version)")

        if missing:
            print(f"\n{Colors.WARNING}Missing dependencies detected!{Colors.ENDC}")
            print("\nPlease install the following tools:\n")
            for tool, info in missing:
                print(f"  {Colors.BOLD}{tool}{Colors.ENDC}: {info['description']}")
                print(f"    Installation: {Colors.OKCYAN}{info['install_url']}{Colors.ENDC}\n")
            return False, missing

        if outdated:
            print(f"\n{Colors.WARNING}Outdated dependencies detected!{Colors.ENDC}")
            print("\nPlease upgrade the following tools:\n")
            for tool, info, installed_version in outdated:
                print(f"  {Colors.BOLD}{tool}{Colors.ENDC}: Installed v{installed_version}, requires >={info['min_version']}")
                print(f"    Installation: {Colors.OKCYAN}{info['install_url']}{Colors.ENDC}\n")
            return False, outdated

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

    @classmethod
    def validate_certificate_chain(cls, cert_content: str, key_content: str, domain: str) -> Tuple[bool, str]:
        """Validate certificate against private key, expiration, and domain"""
        import tempfile
        import datetime

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False) as cert_file, \
                 tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as key_file:
                cert_path = cert_file.name
                key_path = key_file.name
                cert_file.write(cert_content)
                key_file.write(key_content)

            # 1. Check if cert and key match
            cert_modulus = subprocess.run(
                ['openssl', 'x509', '-noout', '-modulus', '-in', cert_path],
                capture_output=True, text=True
            ).stdout
            key_modulus = subprocess.run(
                ['openssl', 'rsa', '-noout', '-modulus', '-in', key_path],
                capture_output=True, text=True
            ).stdout
            if cert_modulus != key_modulus:
                return False, "Certificate and private key do not match."

            # 2. Check expiration
            end_date_str = subprocess.run(
                ['openssl', 'x509', '-noout', '-enddate', '-in', cert_path],
                capture_output=True, text=True
            ).stdout.split('=')[1].strip()
            end_date = datetime.datetime.strptime(end_date_str, '%b %d %H:%M:%S %Y %Z')
            if end_date < datetime.datetime.now():
                return False, f"Certificate expired on {end_date_str}."

            # 3. Check domain name (SAN and CN)
            cert_text = subprocess.run(
                ['openssl', 'x509', '-noout', '-text', '-in', cert_path],
                capture_output=True, text=True
            ).stdout
            
            # Check Subject Alternative Name (SAN)
            import re
            san_match = re.search(r'X509v3 Subject Alternative Name: \n\s*DNS:([^,]+)', cert_text)
            sans = []
            if san_match:
                sans = [name.strip() for name in san_match.group(1).split(', DNS:')]
            
            # Check Common Name (CN)
            cn_match = re.search(r'Subject:.*? CN = ([^/]+)', cert_text)
            cn = cn_match.group(1) if cn_match else None

            valid_domains = set(sans + ([cn] if cn else []))
            
            # Support wildcard domains
            for valid_domain in valid_domains:
                if valid_domain.startswith('*.'):
                    if domain.endswith(valid_domain[1:]) and domain.count('.') == valid_domain.count('.'):
                        return True, "Certificate chain is valid."
                elif domain == valid_domain:
                    return True, "Certificate chain is valid."

            return False, f"Certificate is not valid for domain '{domain}'. Valid domains: {', '.join(valid_domains)}"

        except Exception as e:
            return False, f"An unexpected error occurred during validation: {e}"
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)


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

class GCPAuthChecker:
    """Handles GCP authentication verification"""

    @staticmethod
    def list_projects() -> list:
        """Get list of accessible GCP projects"""
        try:
            result = subprocess.run(
                ['gcloud', 'projects', 'list', '--format=json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                projects = json.loads(result.stdout)
                return [{'projectId': p['projectId'], 'name': p.get('name', p['projectId'])}
                        for p in projects]
            return []
        except subprocess.TimeoutExpired:
            return []
        except Exception:
            return []

    @staticmethod
    def verify_credentials(project_id: str) -> Tuple[bool, str]:
        """Verify GCP credentials work for specified project

        Args:
            project_id: GCP project ID to verify access

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # First check if user is authenticated
            auth_result = subprocess.run(
                ['gcloud', 'auth', 'list', '--format=json'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if auth_result.returncode != 0:
                return False, "Not authenticated with gcloud. Run: gcloud auth login"

            auth_accounts = json.loads(auth_result.stdout)
            active_accounts = [a for a in auth_accounts if a.get('status') == 'ACTIVE']

            if not active_accounts:
                return False, "No active gcloud authentication. Run: gcloud auth login"

            active_email = active_accounts[0].get('account', 'unknown')

            # Verify access to specified project
            project_result = subprocess.run(
                ['gcloud', 'projects', 'describe', project_id, '--format=json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if project_result.returncode == 0:
                project_info = json.loads(project_result.stdout)
                project_name = project_info.get('name', project_id)
                return True, f"Authenticated as {active_email}, Project: {project_name}"
            else:
                return False, f"Cannot access project '{project_id}'. Check permissions or project ID."

        except subprocess.TimeoutExpired:
            return False, "GCP authentication check timed out"
        except json.JSONDecodeError:
            return False, "Failed to parse gcloud output"
        except Exception as e:
            return False, f"Authentication check failed: {str(e)}"

    @staticmethod
    def check_required_apis(project_id: str) -> Tuple[bool, list]:
        """Check if required GCP APIs are enabled

        Args:
            project_id: GCP project ID

        Returns:
            Tuple of (all_enabled: bool, missing_apis: list)
        """
        required_apis = [
            'compute.googleapis.com',
            'container.googleapis.com',
            'cloudresourcemanager.googleapis.com',
            'iam.googleapis.com',
            'iamcredentials.googleapis.com',
            'secretmanager.googleapis.com',
            'sqladmin.googleapis.com',
            'servicenetworking.googleapis.com',
            'logging.googleapis.com',
            'monitoring.googleapis.com',
        ]

        try:
            result = subprocess.run(
                ['gcloud', 'services', 'list', '--enabled',
                 f'--project={project_id}', '--format=json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return False, required_apis

            enabled_services = json.loads(result.stdout)
            enabled_api_names = {svc.get('config', {}).get('name', '') for svc in enabled_services}

            missing = [api for api in required_apis if api not in enabled_api_names]

            return (len(missing) == 0, missing)

        except subprocess.TimeoutExpired:
            return False, required_apis
        except json.JSONDecodeError:
            return False, required_apis
        except Exception:
            return False, required_apis

class ConfigurationPrompt:
    """Handles interactive configuration prompts"""

    def __init__(self, cloud_provider: str = "aws"):
        """Initialize configuration prompt

        Args:
            cloud_provider: Either "aws", "azure", or "gcp"
        """
        self.cloud_provider = cloud_provider
        if cloud_provider == "azure":
            self.config = AzureDeploymentConfig()
        elif cloud_provider == "gcp":
            self.config = GCPDeploymentConfig()
        else:
            self.config = AWSDeploymentConfig()
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

        node_type_choices = [
            "t3.small  (~$30/month for 2 nodes)",
            "t3.medium (~$60/month for 2 nodes) [Recommended]",
            "t3.large  (~$120/month for 2 nodes)"
        ]
        node_type_selection = self.prompt_choice(
            "Node Instance Type",
            node_type_choices,
            default=1
        )
        self.config.node_instance_types = [node_type_selection.split()[0]]

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
            while True:
                key = self.prompt(
                    "Enter existing n8n encryption key (64 hex characters)",
                    required=True
                )
                if len(key) == 64 and all(c in '0123456789abcdefABCDEF' for c in key):
                    self.config.n8n_encryption_key = key
                    break
                else:
                    print(f"{Colors.FAIL}✗ Invalid format. Key must be 64 hexadecimal characters.{Colors.ENDC}")

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

    def collect_azure_configuration(self, skip_tls: bool = True) -> AzureDeploymentConfig:
        """Collect Azure configuration from user

        Args:
            skip_tls: If True, skip TLS configuration (TLS will be configured after LoadBalancer is ready)
        """
        print(f"\n{Colors.HEADER}{Colors.BOLD}N8N Azure AKS Deployment Configuration{Colors.ENDC}")
        print("=" * 60)

        # Azure Configuration
        print(f"\n{Colors.BOLD}Azure Configuration{Colors.ENDC}")

        # Get Azure subscription
        try:
            result = subprocess.run(
                ['az', 'account', 'show', '--query', 'id', '-o', 'tsv'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.config.azure_subscription_id = result.stdout.strip()
                print(f"\n{Colors.OKGREEN}✓ Using Azure subscription: {self.config.azure_subscription_id}{Colors.ENDC}")
            else:
                self.config.azure_subscription_id = self.prompt(
                    "Azure Subscription ID",
                    required=True
                )
        except:
            self.config.azure_subscription_id = self.prompt(
                "Azure Subscription ID",
                required=True
            )

        # Azure Region/Location
        common_locations = [
            "eastus", "eastus2", "westus", "westus2", "centralus",
            "northeurope", "westeurope", "southeastasia", "eastasia"
        ]
        print(f"\nCommon locations: {', '.join(common_locations)}")
        self.config.azure_location = self.prompt(
            "Azure Location (region)",
            default="eastus",
            required=True
        )

        # Resource Group
        self.config.resource_group_name = self.prompt(
            "Resource Group Name",
            default="n8n-rg"
        )

        # AKS Cluster Configuration
        print(f"\n{Colors.BOLD}AKS Cluster Configuration{Colors.ENDC}")

        self.config.cluster_name = self.prompt(
            "AKS Cluster Name",
            default="n8n-aks-cluster"
        )

        # Kubernetes version
        print(f"\nRecommended version: 1.31.11 (supports both Standard and Premium tiers)")
        self.config.kubernetes_version = self.prompt(
            "Kubernetes Version",
            default="1.31.11"
        )

        # VM Size
        vm_size_choices = [
            "Standard_B2s      (~$30/month for 2 nodes)",
            "Standard_D2s_v3   (~$140/month for 2 nodes) [Recommended]",
            "Standard_D4s_v3   (~$280/month for 2 nodes)"
        ]
        vm_size_selection = self.prompt_choice(
            "Node VM Size",
            vm_size_choices,
            default=1
        )
        self.config.node_vm_size = vm_size_selection.split()[0]

        self.config.node_count = int(self.prompt(
            "Initial number of nodes",
            default="2"
        ))

        if self.prompt_yes_no("Enable cluster autoscaling?", default=True):
            self.config.enable_auto_scaling = True
            self.config.node_min_count = int(self.prompt(
                "Minimum number of nodes",
                default="1"
            ))
            self.config.node_max_count = int(self.prompt(
                "Maximum number of nodes",
                default="5"
            ))
        else:
            self.config.enable_auto_scaling = False

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
            while True:
                key = self.prompt(
                    "Enter existing n8n encryption key (64 hex characters)",
                    required=True
                )
                if len(key) == 64 and all(c in '0123456789abcdefABCDEF' for c in key):
                    self.config.n8n_encryption_key = key
                    break
                else:
                    print(f"{Colors.FAIL}✗ Invalid format. Key must be 64 hexadecimal characters.{Colors.ENDC}")

        # Database Configuration
        print(f"\n{Colors.BOLD}Database Configuration{Colors.ENDC}")
        print("\nChoose database backend for n8n:")
        db_choice = self.prompt_choice(
            "Database Type",
            [
                "SQLite (file-based, simpler, lower cost)",
                "PostgreSQL (Azure Flexible Server, production-grade, ~$20-80/month)"
            ],
            default=0
        )

        if "PostgreSQL" in db_choice:
            self.config.database_type = "postgresql"

            postgres_sku_choices = [
                "B_Standard_B1ms  (Burstable, 1vCore, 2GB RAM, ~$20/month)",
                "GP_Standard_D2s_v3 (General Purpose, 2vCore, 8GB RAM, ~$150/month)"
            ]
            sku_selection = self.prompt_choice(
                "PostgreSQL SKU",
                postgres_sku_choices,
                default=0
            )
            self.config.postgres_sku = sku_selection.split()[0]

            self.config.postgres_storage_gb = int(self.prompt(
                "Storage size in GB",
                default="32"
            ))

            self.config.postgres_high_availability = self.prompt_yes_no(
                "Enable zone-redundant high availability? (increases cost)",
                default=False
            )
        else:
            self.config.database_type = "sqlite"

        # Azure Permissions Check
        print(f"\n{Colors.BOLD}Azure Permissions{Colors.ENDC}")
        print("\nAKS LoadBalancer services require the 'Network Contributor' role on the resource group.")
        print("Terraform can automatically create this role assignment, but requires elevated permissions.")
        print(f"\n{Colors.OKCYAN}Do you have 'User Access Administrator' or 'Owner' role?{Colors.ENDC}")

        self.config.terraform_manage_role_assignments = self.prompt_yes_no(
            "Let Terraform manage role assignments?",
            default=True
        )

        if not self.config.terraform_manage_role_assignments:
            print(f"\n{Colors.WARNING}⚠  You'll need to manually create role assignments BEFORE running Terraform:{Colors.ENDC}")
            print(f"{Colors.OKCYAN}   # Network Contributor (required for LoadBalancer):{Colors.ENDC}")
            print(f"{Colors.OKCYAN}   az role assignment create --role \"Network Contributor\" \\{Colors.ENDC}")
            print(f"{Colors.OKCYAN}     --assignee $(az aks show -g <resource-group> -n <cluster-name> --query \"identity.principalId\" -o tsv) \\{Colors.ENDC}")
            print(f"{Colors.OKCYAN}     --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>{Colors.ENDC}")
            print(f"\n{Colors.OKCYAN}   # Key Vault Secrets User (required for Key Vault access):{Colors.ENDC}")
            print(f"{Colors.OKCYAN}   az role assignment create --role \"Key Vault Secrets User\" \\{Colors.ENDC}")
            print(f"{Colors.OKCYAN}     --assignee $(az aks show -g <resource-group> -n <cluster-name> --query \"keyVaultSecretsProvider.secretIdentity.objectId\" -o tsv) \\{Colors.ENDC}")
            print(f"{Colors.OKCYAN}     --scope $(az keyvault show -g <resource-group> -n <keyvault-name> --query id -o tsv){Colors.ENDC}")

        # Static IP Configuration
        print(f"\n{Colors.BOLD}LoadBalancer IP Configuration{Colors.ENDC}")
        print("\nChoose LoadBalancer IP allocation:")
        print(f"{Colors.OKCYAN}• Static IP:{Colors.ENDC} Pre-allocated, survives cluster rebuilds")
        print(f"{Colors.OKCYAN}• Dynamic IP:{Colors.ENDC} Azure auto-assigns, IP may change on cluster rebuild")

        self.config.use_static_ip = self.prompt_yes_no(
            "Use static IP? (Recommended for production)",
            default=False
        )

        # Protocol (HTTP vs HTTPS)
        if self.prompt_yes_no("\nEnable HTTPS/TLS?", default=False):
            self.config.n8n_protocol = "https"
            self.config.enable_cert_manager = self.prompt_yes_no(
                "Install cert-manager for automatic TLS certificates?",
                default=False
            )
            if self.config.enable_cert_manager:
                self.config.letsencrypt_email = self.prompt(
                    "Email for Let's Encrypt notifications",
                    required=True
                )
        else:
            self.config.n8n_protocol = "http"

        # Basic Authentication
        if self.prompt_yes_no("\nEnable basic authentication (username/password)?", default=False):
            self.config.enable_basic_auth = True
            self.config.basic_auth_username = self.prompt(
                "Basic auth username",
                default="admin"
            )
            while True:
                password = self.prompt(
                    "Basic auth password (min 8 characters)",
                    required=True
                )
                if len(password) >= 8:
                    self.config.basic_auth_password = password
                    break
                else:
                    print(f"{Colors.FAIL}✗ Password must be at least 8 characters{Colors.ENDC}")
        else:
            self.config.enable_basic_auth = False

        # Show configuration summary
        print(f"\n{Colors.HEADER}{Colors.BOLD}Configuration Summary{Colors.ENDC}")
        print("=" * 60)
        print(f"Subscription:    {Colors.OKCYAN}{self.config.azure_subscription_id}{Colors.ENDC}")
        print(f"Location:        {Colors.OKCYAN}{self.config.azure_location}{Colors.ENDC}")
        print(f"Resource Group:  {Colors.OKCYAN}{self.config.resource_group_name}{Colors.ENDC}")
        print(f"AKS Cluster:     {Colors.OKCYAN}{self.config.cluster_name}{Colors.ENDC}")
        print(f"K8s Version:     {Colors.OKCYAN}{self.config.kubernetes_version}{Colors.ENDC}")
        print(f"VM Size:         {Colors.OKCYAN}{self.config.node_vm_size}{Colors.ENDC}")
        print(f"Node Count:      {Colors.OKCYAN}{self.config.node_count}{Colors.ENDC}")
        if self.config.enable_auto_scaling:
            print(f"Autoscaling:     {Colors.OKCYAN}{self.config.node_min_count}-{self.config.node_max_count} nodes{Colors.ENDC}")
        print(f"N8N Host:        {Colors.OKCYAN}{self.config.n8n_host}{Colors.ENDC}")
        print(f"Protocol:        {Colors.OKCYAN}{self.config.n8n_protocol.upper()}{Colors.ENDC}")
        print(f"Namespace:       {Colors.OKCYAN}{self.config.n8n_namespace}{Colors.ENDC}")
        print(f"PVC Size:        {Colors.OKCYAN}{self.config.n8n_persistence_size}{Colors.ENDC}")
        print(f"Timezone:        {Colors.OKCYAN}{self.config.timezone}{Colors.ENDC}")
        print(f"Encryption Key:  {Colors.OKCYAN}{'*' * 20} (hidden){Colors.ENDC}")
        print(f"Database Type:   {Colors.OKCYAN}{self.config.database_type.upper()}{Colors.ENDC}")
        if self.config.database_type == "postgresql":
            print(f"  PostgreSQL SKU: {Colors.OKCYAN}{self.config.postgres_sku}{Colors.ENDC}")
            print(f"  Storage:        {Colors.OKCYAN}{self.config.postgres_storage_gb}GB{Colors.ENDC}")
            print(f"  High Avail:     {Colors.OKCYAN}{'Yes' if self.config.postgres_high_availability else 'No'}{Colors.ENDC}")
        print("=" * 60)
        print(f"\n{Colors.WARNING}Note: TLS and Basic Auth will be configured after deployment{Colors.ENDC}")

        return self.config

    def collect_gcp_configuration(self, skip_tls: bool = True) -> GCPDeploymentConfig:
        """Collect GCP configuration from user

        Args:
            skip_tls: If True, skip TLS configuration (TLS will be configured after LoadBalancer is ready)
        """
        print(f"\n{Colors.HEADER}{Colors.BOLD}N8N GCP GKE Deployment Configuration{Colors.ENDC}")
        print("=" * 60)

        # GCP Configuration
        print(f"\n{Colors.BOLD}GCP Configuration{Colors.ENDC}")

        # Step 1: List and select GCP project
        projects = GCPAuthChecker.list_projects()
        if not projects:
            print(f"\n{Colors.FAIL}✗ No GCP projects found{Colors.ENDC}")
            print("\nPlease authenticate with GCP first:")
            print(f"  {Colors.OKCYAN}gcloud auth login{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}gcloud config set project <project-id>{Colors.ENDC}")
            raise SetupInterrupted("GCP authentication required")

        if len(projects) == 1:
            selected_project = projects[0]['projectId']
            print(f"\n{Colors.OKGREEN}✓ Using project: {projects[0]['name']} ({selected_project}){Colors.ENDC}")
        else:
            print(f"\nAvailable GCP projects:")
            project_choices = [f"{p['name']} ({p['projectId']})" for p in projects]
            selection = self.prompt_choice(
                "Select GCP Project",
                project_choices,
                default=0
            )
            # Extract project ID from selection (format: "Name (project-id)")
            selected_project = selection.split('(')[1].rstrip(')')

        self.config = GCPDeploymentConfig()
        self.config.gcp_project_id = selected_project

        # Step 2: Verify credentials
        print(f"\n{Colors.HEADER}🔐 Verifying GCP credentials...{Colors.ENDC}")
        success, message = GCPAuthChecker.verify_credentials(self.config.gcp_project_id)

        if success:
            print(f"{Colors.OKGREEN}✓ GCP credentials verified{Colors.ENDC}")
            print(f"  {message}")
        else:
            print(f"{Colors.FAIL}✗ GCP authentication failed{Colors.ENDC}")
            print(f"  {message}")
            print(f"\n{Colors.WARNING}Please authenticate with GCP:{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}gcloud auth login{Colors.ENDC}")
            print(f"  {Colors.OKCYAN}gcloud config set project {self.config.gcp_project_id}{Colors.ENDC}")
            raise SetupInterrupted("GCP authentication required")

        # Step 3: Check and optionally enable required APIs
        print(f"\n{Colors.HEADER}🔍 Checking required GCP APIs...{Colors.ENDC}")
        apis_ok, missing_apis = GCPAuthChecker.check_required_apis(self.config.gcp_project_id)

        if not apis_ok:
            print(f"{Colors.WARNING}⚠  The following APIs need to be enabled:{Colors.ENDC}")
            for api in missing_apis:
                print(f"  • {api}")

            if self.prompt_yes_no("\nEnable required APIs now? (may take 1-2 minutes)", default=True):
                print(f"\n{Colors.HEADER}Enabling APIs...{Colors.ENDC}")
                for api in missing_apis:
                    try:
                        print(f"  Enabling {api}...")
                        result = subprocess.run(
                            ['gcloud', 'services', 'enable', api,
                             '--project', self.config.gcp_project_id],
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                        if result.returncode == 0:
                            print(f"  {Colors.OKGREEN}✓ {api} enabled{Colors.ENDC}")
                        else:
                            print(f"  {Colors.FAIL}✗ Failed to enable {api}{Colors.ENDC}")
                    except subprocess.TimeoutExpired:
                        print(f"  {Colors.WARNING}⚠ Timeout enabling {api} (may still succeed in background){Colors.ENDC}")
                    except Exception as e:
                        print(f"  {Colors.FAIL}✗ Error enabling {api}: {e}{Colors.ENDC}")
                print(f"\n{Colors.OKGREEN}✓ API enablement complete{Colors.ENDC}")
            else:
                print(f"\n{Colors.WARNING}You'll need to manually enable these APIs:{Colors.ENDC}")
                for api in missing_apis:
                    print(f"  {Colors.OKCYAN}gcloud services enable {api} --project {self.config.gcp_project_id}{Colors.ENDC}")
                if not self.prompt_yes_no("\nContinue anyway?", default=False):
                    raise SetupInterrupted("Required APIs not enabled")
        else:
            print(f"{Colors.OKGREEN}✓ All required APIs are enabled{Colors.ENDC}")

        # Step 4: Select region
        common_regions = [
            "us-central1", "us-east1", "us-west1",
            "europe-west1", "asia-southeast1"
        ]
        print(f"\nCommon regions: {', '.join(common_regions)}")
        self.config.gcp_region = self.prompt(
            "GCP Region",
            default="us-central1",
            required=True
        )

        # Step 5: Select zone (auto-append -a)
        self.config.gcp_zone = f"{self.config.gcp_region}-a"
        print(f"Zone: {Colors.OKCYAN}{self.config.gcp_zone}{Colors.ENDC}")

        # Step 6: Cluster configuration
        print(f"\n{Colors.BOLD}GKE Cluster Configuration{Colors.ENDC}")

        self.config.cluster_name = self.prompt(
            "GKE Cluster Name",
            default="n8n-gke-cluster"
        )

        machine_type_choices = [
            "e2-micro       (~$6/month for 1 node, minimal)",
            "e2-small       (~$13/month for 1 node)",
            "e2-medium      (~$27/month for 1 node) [Recommended]",
            "n1-standard-1  (~$25/month for 1 node)",
            "n1-standard-2  (~$49/month for 1 node)"
        ]
        machine_selection = self.prompt_choice(
            "Node Machine Type",
            machine_type_choices,
            default=2
        )
        self.config.node_machine_type = machine_selection.split()[0]

        self.config.node_count = int(self.prompt(
            "Number of nodes",
            default="1"
        ))

        # VPC naming
        self.config.vpc_name = self.prompt(
            "VPC Network Name",
            default="n8n-vpc"
        )

        self.config.subnet_name = self.prompt(
            "Subnet Name",
            default="n8n-subnet"
        )

        # Step 7: N8N Configuration
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
            while True:
                key = self.prompt(
                    "Enter existing n8n encryption key (64 hex characters)",
                    required=True
                )
                if len(key) == 64 and all(c in '0123456789abcdefABCDEF' for c in key):
                    self.config.n8n_encryption_key = key
                    break
                else:
                    print(f"{Colors.FAIL}✗ Invalid format. Key must be 64 hexadecimal characters.{Colors.ENDC}")

        # Step 8: Database Configuration
        print(f"\n{Colors.BOLD}Database Configuration{Colors.ENDC}")
        print("\nChoose database backend for n8n:")
        db_choice = self.prompt_choice(
            "Database Type",
            [
                "SQLite (file-based, simpler, lower cost)",
                "Cloud SQL PostgreSQL (managed, production-grade, ~$25-80/month)"
            ],
            default=0
        )

        if "Cloud SQL" in db_choice:
            self.config.database_type = "cloudsql"

            self.config.cloudsql_instance_name = self.prompt(
                "Cloud SQL Instance Name",
                default="n8n-postgres"
            )

            cloudsql_tier_choices = [
                "db-f1-micro      (Shared CPU, 614MB RAM, ~$25/month)",
                "db-g1-small      (Shared CPU, 1.7GB RAM, ~$50/month)",
                "db-n1-standard-1 (1 vCPU, 3.75GB RAM, ~$80/month)"
            ]
            tier_selection = self.prompt_choice(
                "Cloud SQL Tier",
                cloudsql_tier_choices,
                default=0
            )
            self.config.cloudsql_tier = tier_selection.split()[0]

            print(f"\n{Colors.OKGREEN}✓ Cloud SQL PostgreSQL will be provisioned{Colors.ENDC}")
        else:
            self.config.database_type = "sqlite"
            print(f"\n{Colors.OKGREEN}✓ SQLite will be used (file-based on persistent disk){Colors.ENDC}")

        # Step 9: TLS Configuration (if not skip_tls)
        if not skip_tls:
            print(f"\n{Colors.BOLD}TLS/HTTPS Configuration{Colors.ENDC}")
            if self.prompt_yes_no("\nEnable HTTPS/TLS?", default=False):
                self.config.n8n_protocol = "https"
                self.config.enable_tls = True
                self.config.tls_provider = "letsencrypt"

                self.config.letsencrypt_email = self.prompt(
                    "Email for Let's Encrypt notifications",
                    required=True
                )
            else:
                self.config.n8n_protocol = "http"
                self.config.enable_tls = False
        else:
            self.config.n8n_protocol = "http"
            self.config.enable_tls = False

        # Step 10: Basic Authentication (if not skip_tls)
        if not skip_tls:
            print(f"\n{Colors.BOLD}Basic Authentication{Colors.ENDC}")
            if self.prompt_yes_no("\nEnable basic authentication (username/password)?", default=False):
                self.config.enable_basic_auth = True
                self.config.basic_auth_username = self.prompt(
                    "Basic auth username",
                    default="admin"
                )
                while True:
                    password = self.prompt(
                        "Basic auth password (min 8 characters)",
                        required=True
                    )
                    if len(password) >= 8:
                        self.config.basic_auth_password = password
                        break
                    else:
                        print(f"{Colors.FAIL}✗ Password must be at least 8 characters{Colors.ENDC}")
            else:
                self.config.enable_basic_auth = False
        else:
            self.config.enable_basic_auth = False

        # Show configuration summary
        print(f"\n{Colors.HEADER}{Colors.BOLD}Configuration Summary{Colors.ENDC}")
        print("=" * 60)
        print(f"Project ID:      {Colors.OKCYAN}{self.config.gcp_project_id}{Colors.ENDC}")
        print(f"Region:          {Colors.OKCYAN}{self.config.gcp_region}{Colors.ENDC}")
        print(f"Zone:            {Colors.OKCYAN}{self.config.gcp_zone}{Colors.ENDC}")
        print(f"GKE Cluster:     {Colors.OKCYAN}{self.config.cluster_name}{Colors.ENDC}")
        print(f"Machine Type:    {Colors.OKCYAN}{self.config.node_machine_type}{Colors.ENDC}")
        print(f"Node Count:      {Colors.OKCYAN}{self.config.node_count}{Colors.ENDC}")
        print(f"VPC:             {Colors.OKCYAN}{self.config.vpc_name}{Colors.ENDC}")
        print(f"Subnet:          {Colors.OKCYAN}{self.config.subnet_name}{Colors.ENDC}")
        print(f"N8N Host:        {Colors.OKCYAN}{self.config.n8n_host}{Colors.ENDC}")
        print(f"Protocol:        {Colors.OKCYAN}{self.config.n8n_protocol.upper()}{Colors.ENDC}")
        print(f"Namespace:       {Colors.OKCYAN}{self.config.n8n_namespace}{Colors.ENDC}")
        print(f"Timezone:        {Colors.OKCYAN}{self.config.timezone}{Colors.ENDC}")
        print(f"Encryption Key:  {Colors.OKCYAN}{'*' * 20} (hidden){Colors.ENDC}")
        print(f"Database Type:   {Colors.OKCYAN}{self.config.database_type.upper()}{Colors.ENDC}")
        if self.config.database_type == "cloudsql":
            print(f"  Instance Name: {Colors.OKCYAN}{self.config.cloudsql_instance_name}{Colors.ENDC}")
            print(f"  Tier:          {Colors.OKCYAN}{self.config.cloudsql_tier}{Colors.ENDC}")
        print("=" * 60)

        if skip_tls:
            print(f"\n{Colors.WARNING}Note: TLS and Basic Auth will be configured after deployment{Colors.ENDC}")

        if not self.prompt_yes_no("\nProceed with this configuration?", default=True):
            raise SetupInterrupted("Configuration cancelled by user")

        return self.config

class FileUpdater:
    """Handles updating Terraform and Helm configuration files"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.terraform_dir = base_dir / "terraform" / "aws"
        self.helm_dir = base_dir / "charts" / "n8n"
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

        replacements = {
            "region": config.aws_region,
            "cluster_name": config.cluster_name,
            "n8n_namespace": config.n8n_namespace,
            "n8n_host": config.n8n_host,
            "timezone": config.timezone,
            "n8n_persistence_size": config.n8n_persistence_size,
        }

        for var_name, value in replacements.items():
            if value:
                content = self._update_variable_default(content, var_name, str(value))

        variables_file.write_text(content)
        print(f"{Colors.OKGREEN}✓ Updated terraform/aws/variables.tf{Colors.ENDC}")

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
            f'enable_nginx_ingress = {"true" if config.enable_nginx_ingress else "false"}',
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
        print(f"{Colors.OKGREEN}✓ Created terraform/aws/terraform.tfvars{Colors.ENDC}")

    def create_terraform_tfvars_azure(self, config: AzureDeploymentConfig):
        """Create terraform.tfvars for Azure AKS infrastructure deployment"""
        tfvars_file = self.base_dir / "terraform" / "azure" / "terraform.tfvars"

        lines = [
            "# Auto-generated by setup.py - N8N Azure AKS Infrastructure",
            f'azure_subscription_id = "{config.azure_subscription_id}"',
            f'azure_location        = "{config.azure_location}"',
            f'resource_group_name   = "{config.resource_group_name}"',
            f'project_tag           = "n8n-app"',
            "",
            "# AKS Cluster",
            f'cluster_name       = "{config.cluster_name}"',
            f'kubernetes_version = "{config.kubernetes_version}"',
            f'node_vm_size       = "{config.node_vm_size}"',
            f'node_count         = {config.node_count}',
            f'node_min_count     = {config.node_min_count}',
            f'node_max_count     = {config.node_max_count}',
            f'enable_auto_scaling = {str(config.enable_auto_scaling).lower()}',
            "",
            "# Application",
            f'n8n_host              = "{config.n8n_host}"',
            f'n8n_namespace         = "{config.n8n_namespace}"',
            f'n8n_protocol          = "{config.n8n_protocol}"',
            f'timezone              = "{config.timezone}"',
            f'n8n_persistence_size  = "{config.n8n_persistence_size}"',
            f'n8n_encryption_key    = "{config.n8n_encryption_key}"',
            "",
            "# Database",
            f'database_type = "{config.database_type}"',
        ]

        if config.database_type == "postgresql":
            lines.extend([
                f'postgres_sku                = "{config.postgres_sku}"',
                f'postgres_storage_gb         = {config.postgres_storage_gb}',
                f'postgres_high_availability  = {str(config.postgres_high_availability).lower()}',
            ])

        lines.extend([
            "",
            "# Optional Features",
            f'use_static_ip                      = {str(config.use_static_ip).lower()}',
            f'enable_nginx_ingress               = {str(config.enable_nginx_ingress).lower()}',
            f'enable_basic_auth                  = {str(config.enable_basic_auth).lower()}',
            f'enable_cert_manager                = {str(config.enable_cert_manager).lower()}',
            f'terraform_manage_role_assignments  = {str(config.terraform_manage_role_assignments).lower()}',
        ])

        tfvars_file.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(lines) + "\n"
        tfvars_file.write_text(content)
        print(f"{Colors.OKGREEN}✓ Created terraform/azure/terraform.tfvars{Colors.ENDC}")

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
        print(f"{Colors.OKGREEN}✓ Updated charts/n8n/values.yaml{Colors.ENDC}")

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
            # Keep Terraform and Helm defaults aligned with the chosen configuration
            self.update_terraform_variables(config)
            self.update_helm_values(config)
            # Create terraform.tfvars
            self.create_terraform_tfvars(config)

            print(f"{Colors.OKGREEN}✓ All configuration files updated{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}✗ Error updating files: {e}{Colors.ENDC}")
            self.restore_backup()
            raise


def load_existing_configuration(script_dir: Path, cloud_provider: str = "aws") -> DeploymentConfig:
    """Load deployment values from terraform/{cloud_provider}/terraform.tfvars"""
    tfvars_path = script_dir / "terraform" / cloud_provider / "terraform.tfvars"

    if not tfvars_path.exists():
        raise FileNotFoundError(f"terraform/{cloud_provider}/terraform.tfvars not found; run initial setup first")

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
        elif key == 'node_min_size':
            config.node_min_size = int(parsed)
        elif key == 'node_max_size':
            config.node_max_size = int(parsed)
        elif key == 'n8n_host':
            config.n8n_host = str(parsed)
        elif key == 'timezone':
            config.timezone = str(parsed)
        elif key == 'n8n_encryption_key':
            config.n8n_encryption_key = str(parsed)
        elif key == 'n8n_namespace':
            config.n8n_namespace = str(parsed)
        elif key == 'n8n_persistence_size':
            config.n8n_persistence_size = str(parsed)
        elif key == 'enable_nginx_ingress':
            config.enable_nginx_ingress = bool(parsed)

    if not config.n8n_host:
        raise ValueError("n8n_host is missing in terraform.tfvars")

    return config


def save_state_for_region(terraform_dir: Path, region: str) -> bool:
    """
    Save current terraform state file with region/location-specific naming.

    Args:
        terraform_dir: Path to terraform directory
        region: AWS region (e.g., 'us-west-1') or Azure location (e.g., 'eastus')

    Returns:
        True if state was saved successfully, False otherwise
    """
    tfstate_path = terraform_dir / "terraform.tfstate"

    # Check if state file exists and has resources
    if not tfstate_path.exists():
        print(f"{Colors.WARNING}⚠  No terraform state file found, nothing to save{Colors.ENDC}")
        return False

    # Check if state has resources (not empty state)
    try:
        with open(tfstate_path, 'r') as f:
            state_data = json.load(f)
            if not state_data.get('resources'):
                print(f"{Colors.WARNING}⚠  Terraform state is empty (no resources), skipping backup{Colors.ENDC}")
                return False
    except (json.JSONDecodeError, Exception) as e:
        print(f"{Colors.WARNING}⚠  Could not read state file: {e}{Colors.ENDC}")
        return False

    # Create region-specific backup
    backup_path = terraform_dir / f"terraform.tfstate.{region}.backup"

    try:
        shutil.copy2(tfstate_path, backup_path)
        print(f"{Colors.OKGREEN}✓ Saved state for region {region} to {backup_path.name}{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"{Colors.FAIL}✗ Failed to save state: {e}{Colors.ENDC}")
        return False


def restore_state_for_region(terraform_dir: Path, region: str) -> bool:
    """
    Restore terraform state from region/location-specific backup.

    Args:
        terraform_dir: Path to terraform directory
        region: AWS region (e.g., 'us-west-1') or Azure location (e.g., 'eastus')

    Returns:
        True if state was restored successfully, False otherwise
    """
    backup_path = terraform_dir / f"terraform.tfstate.{region}.backup"
    tfstate_path = terraform_dir / "terraform.tfstate"

    if not backup_path.exists():
        print(f"{Colors.FAIL}✗ No backup found for region {region}{Colors.ENDC}")
        print(f"{Colors.OKCYAN}Available backups:{Colors.ENDC}")
        list_available_state_backups(terraform_dir)
        return False

    # Backup current state before overwriting (if it exists and has resources)
    if tfstate_path.exists():
        try:
            with open(tfstate_path, 'r') as f:
                state_data = json.load(f)
                if state_data.get('resources'):
                    # Save current state with timestamp
                    timestamp = int(time.time())
                    temp_backup = terraform_dir / f"terraform.tfstate.{timestamp}.backup"
                    shutil.copy2(tfstate_path, temp_backup)
                    print(f"{Colors.OKCYAN}  Current state backed up to {temp_backup.name}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}⚠  Could not backup current state: {e}{Colors.ENDC}")

    # Restore the region-specific backup
    try:
        shutil.copy2(backup_path, tfstate_path)
        print(f"{Colors.OKGREEN}✓ Restored state for region {region} from {backup_path.name}{Colors.ENDC}")

        # Show what was restored
        try:
            with open(tfstate_path, 'r') as f:
                state_data = json.load(f)
                resource_count = len(state_data.get('resources', []))
                print(f"{Colors.OKCYAN}  State contains {resource_count} resources{Colors.ENDC}")
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"{Colors.FAIL}✗ Failed to restore state: {e}{Colors.ENDC}")
        return False


def list_available_state_backups(terraform_dir: Path):
    """List all available region-specific state backups."""
    backups = sorted(terraform_dir.glob("terraform.tfstate.*.backup"))

    if not backups:
        print(f"  {Colors.WARNING}No region-specific backups found{Colors.ENDC}")
        return

    for backup in backups:
        # Try to extract region from filename
        filename = backup.name
        # Pattern: terraform.tfstate.REGION.backup or terraform.tfstate.TIMESTAMP.backup
        parts = filename.replace("terraform.tfstate.", "").replace(".backup", "")

        # Check if it's a region name (contains letters) vs timestamp (only numbers)
        if parts and not parts.isdigit():
            # Try to read the backup to get info
            try:
                with open(backup, 'r') as f:
                    state_data = json.load(f)
                    resource_count = len(state_data.get('resources', []))
                    file_size = backup.stat().st_size

                    # Try to find EKS cluster ARN for confirmation
                    region_from_arn = None
                    for resource in state_data.get('resources', []):
                        if resource.get('type') == 'aws_eks_cluster':
                            instances = resource.get('instances', [])
                            if instances:
                                arn = instances[0].get('attributes', {}).get('arn', '')
                                if arn:
                                    # ARN format: arn:aws:eks:REGION:...
                                    region_from_arn = arn.split(':')[3] if len(arn.split(':')) > 3 else None
                                    break

                    region_display = f"{parts}"
                    if region_from_arn and region_from_arn != parts:
                        region_display = f"{parts} (contains {region_from_arn} resources)"

                    print(f"  • {region_display}: {resource_count} resources, {file_size/1024:.1f}KB")
            except Exception:
                print(f"  • {parts}: (unable to read)")


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
                # Ensure namespace exists before creating secret
                namespace_check = subprocess.run(
                    ['kubectl', 'get', 'namespace', namespace],
                    capture_output=True
                )
                if namespace_check.returncode != 0:
                    # Create namespace if it doesn't exist
                    result = subprocess.run(
                        ['kubectl', 'create', 'namespace', namespace],
                        capture_output=True, text=True
                    )
                    if result.returncode != 0:
                        print(f"{Colors.FAIL}✗ Failed to create namespace {namespace}{Colors.ENDC}")
                        print(result.stderr)
                        return False
                    print(f"{Colors.OKGREEN}  ✓ Created namespace {namespace}{Colors.ENDC}")

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
                # Enable SSL for RDS connections (required by AWS RDS)
                '--set', 'env.DB_POSTGRESDB_SSL_ENABLED=true',
                '--set', 'env.DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED=false',
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

def verify_n8n_deployment(namespace: str, timeout_seconds: int = 300) -> bool:
    """Verify that the n8n deployment is ready"""
    print(f"\n{Colors.HEADER}⏳ Waiting for n8n deployment to be ready...{Colors.ENDC}")
    import time

    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            result = subprocess.run(
                ['kubectl', 'get', 'deployment', 'n8n', '-n', namespace, '-o', 'json'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                status = json.loads(result.stdout).get('status', {})
                replicas = status.get('replicas', 0)
                ready_replicas = status.get('readyReplicas', 0)

                if replicas > 0 and replicas == ready_replicas:
                    print(f"{Colors.OKGREEN}✓ n8n deployment is ready with {ready_replicas}/{replicas} pods.{Colors.ENDC}")
                    return True
                else:
                    print(f"  - Waiting... ({ready_replicas}/{replicas} pods ready)")
            else:
                print(f"  - {Colors.WARNING}Could not get deployment status. Retrying...{Colors.ENDC}")

        except Exception as e:
            print(f"  - {Colors.WARNING}An error occurred while checking status: {e}{Colors.ENDC}")

        time.sleep(15)

    print(f"{Colors.FAIL}✗ Timed out waiting for n8n deployment to become ready.{Colors.ENDC}")
    return False

def get_loadbalancer_url(max_attempts: int = 30, delay: int = 10) -> Optional[str]:
    """Get the LoadBalancer URL from NGINX ingress controller

    Args:
        max_attempts: Maximum number of attempts to get the URL
        delay: Delay in seconds between attempts

    Returns:
        LoadBalancer DNS name or IP address, or None if not found
    """
    print(f"\n{Colors.HEADER}⏳ Waiting for LoadBalancer to be ready...{Colors.ENDC}")

    for attempt in range(1, max_attempts + 1):
        try:
            # Try hostname first (AWS ELB)
            result_hostname = subprocess.run(
                ['kubectl', 'get', 'svc', '-n', 'ingress-nginx', 'ingress-nginx-controller',
                 '-o', 'jsonpath={.status.loadBalancer.ingress[0].hostname}'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result_hostname.returncode == 0 and result_hostname.stdout.strip():
                lb_url = result_hostname.stdout.strip()
                print(f"{Colors.OKGREEN}✓ LoadBalancer ready: {lb_url}{Colors.ENDC}")
                return lb_url

            # Try IP address (Azure, GCP)
            result_ip = subprocess.run(
                ['kubectl', 'get', 'svc', '-n', 'ingress-nginx', 'ingress-nginx-controller',
                 '-o', 'jsonpath={.status.loadBalancer.ingress[0].ip}'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result_ip.returncode == 0 and result_ip.stdout.strip():
                lb_url = result_ip.stdout.strip()
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

        # Validate the certificate chain
        print(f"\n{Colors.HEADER}🔬 Validating certificate chain...{Colors.ENDC}")
        valid, message = CertificateValidator.validate_certificate_chain(
            config.tls_certificate_crt,
            config.tls_certificate_key,
            config.n8n_host
        )
        if not valid:
            print(f"{Colors.FAIL}✗ Certificate validation failed: {message}{Colors.ENDC}")
            # Allow user to retry
            if prompt.prompt_yes_no("Try again with different files?", default=True):
                 # This is a bit tricky in the current structure. For simplicity, we'll exit and ask them to re-run.
                 print("Please re-run the script with the --configure-tls flag to try again.")
                 return False # Abort the TLS setup
            else:
                 return False

        print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

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

        # Install cert-manager (check if already installed)
        print(f"\n{Colors.HEADER}Installing cert-manager...{Colors.ENDC}")
        try:
            # Check if cert-manager is already installed
            check_result = subprocess.run([
                'helm', 'list', '-n', 'cert-manager', '-o', 'json'
            ], capture_output=True, text=True, timeout=30)

            cert_manager_installed = False
            if check_result.returncode == 0:
                releases = json.loads(check_result.stdout)
                cert_manager_installed = any(r.get('name') == 'cert-manager' for r in releases)

            if cert_manager_installed:
                print(f"{Colors.OKGREEN}✓ cert-manager already installed{Colors.ENDC}")
            else:
                # Install cert-manager
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
    helm_runner = HelmRunner(script_dir / "charts" / "n8n")

    # Get encryption key from outputs
    tf_runner = TerraformRunner(script_dir / "terraform" / "aws")
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
    import string

    alphabet = string.ascii_letters + string.digits
    config.basic_auth_password = ''.join(secrets.choice(alphabet) for _ in range(12))

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
            'helm', 'upgrade', 'n8n', str(script_dir / 'charts' / 'n8n'),
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

    # Update configuration state
    config.enable_basic_auth = True

    # Update terraform.tfvars to track basic auth state for proper cleanup
    try:
        tfvars_path = script_dir / "terraform" / "aws" / "terraform.tfvars"
        if tfvars_path.exists():
            content = tfvars_path.read_text()
            # Update enable_basic_auth value
            import re
            content = re.sub(
                r'enable_basic_auth\s*=\s*(true|false)',
                'enable_basic_auth  = true',
                content
            )
            tfvars_path.write_text(content)
            print(f"{Colors.OKGREEN}✓ Updated terraform.tfvars with basic auth state{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.WARNING}⚠ Could not update terraform.tfvars: {e}{Colors.ENDC}")
        print(f"{Colors.WARNING}  Basic auth is enabled but not tracked in Terraform state{Colors.ENDC}")

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ Basic Authentication Configured!{Colors.ENDC}")
    print("\n" + "=" * 60)
    print(f"Basic auth is now required to access n8n")
    print(f"Username: {Colors.OKCYAN}{config.basic_auth_username}{Colors.ENDC}")
    print(f"Password: {Colors.OKCYAN}{config.basic_auth_password}{Colors.ENDC}")
    print("=" * 60)

    return True

class TeardownRunner:
    """Handles teardown of N8N EKS deployment"""

    def __init__(self, script_dir: Path, config: DeploymentConfig):
        self.script_dir = script_dir
        self.config = config
        self.terraform_dir = script_dir / "terraform" / "aws"

    def phase1_helm_releases(self) -> bool:
        """Phase 1: Uninstall Helm releases"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}📦 PHASE 1: Uninstalling Helm Releases{Colors.ENDC}")
        print("=" * 60)

        # Check if cluster is accessible
        try:
            result = subprocess.run(
                ['kubectl', 'cluster-info'],
                capture_output=True,
                timeout=10
            )
            if result.returncode != 0:
                print(f"{Colors.WARNING}⚠  Cluster not accessible, skipping Helm cleanup{Colors.ENDC}")
                print(f"{Colors.WARNING}  If cluster still exists, manually uninstall: helm uninstall n8n -n {self.config.n8n_namespace}{Colors.ENDC}")
                return True
        except Exception as e:
            print(f"{Colors.WARNING}⚠  Cannot verify cluster access: {e}{Colors.ENDC}")
            return True

        success = True

        # Uninstall n8n
        print(f"\n{Colors.OKCYAN}Checking for n8n Helm release...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['helm', 'list', '-n', self.config.n8n_namespace, '-o', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                releases = json.loads(result.stdout) if result.stdout.strip() else []
                n8n_found = any(r.get('name') == 'n8n' for r in releases)

                if n8n_found:
                    print(f"{Colors.OKCYAN}  Uninstalling n8n...{Colors.ENDC}")
                    result = subprocess.run(
                        ['helm', 'uninstall', 'n8n', '-n', self.config.n8n_namespace],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode == 0:
                        print(f"{Colors.OKGREEN}  ✓ n8n uninstalled{Colors.ENDC}")
                    else:
                        print(f"{Colors.FAIL}  ✗ Failed to uninstall n8n{Colors.ENDC}")
                        print(f"  {result.stderr}")
                        success = False
                else:
                    print(f"{Colors.OKCYAN}  n8n Helm release not found{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}  Error checking n8n release: {e}{Colors.ENDC}")
            success = False

        # Uninstall ingress-nginx
        print(f"\n{Colors.OKCYAN}Checking for ingress-nginx Helm release...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['helm', 'list', '-n', 'ingress-nginx', '-o', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                releases = json.loads(result.stdout) if result.stdout.strip() else []
                nginx_found = any(r.get('name') == 'ingress-nginx' for r in releases)

                if nginx_found:
                    print(f"{Colors.OKCYAN}  Uninstalling ingress-nginx...{Colors.ENDC}")
                    result = subprocess.run(
                        ['helm', 'uninstall', 'ingress-nginx', '-n', 'ingress-nginx'],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode == 0:
                        print(f"{Colors.OKGREEN}  ✓ ingress-nginx uninstalled{Colors.ENDC}")
                        print(f"{Colors.OKCYAN}  Waiting for LoadBalancer to be deleted...{Colors.ENDC}")
                        import time
                        time.sleep(30)
                    else:
                        print(f"{Colors.FAIL}  ✗ Failed to uninstall ingress-nginx{Colors.ENDC}")
                        print(f"  {result.stderr}")
                        success = False
                else:
                    print(f"{Colors.OKCYAN}  ingress-nginx Helm release not found{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}  Error checking ingress-nginx release: {e}{Colors.ENDC}")
            success = False

        # Uninstall cert-manager if exists
        print(f"\n{Colors.OKCYAN}Checking for cert-manager Helm release...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['helm', 'list', '-n', 'cert-manager', '-o', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                releases = json.loads(result.stdout) if result.stdout.strip() else []
                cert_manager_found = any(r.get('name') == 'cert-manager' for r in releases)

                if cert_manager_found:
                    print(f"{Colors.OKCYAN}  Uninstalling cert-manager...{Colors.ENDC}")
                    result = subprocess.run(
                        ['helm', 'uninstall', 'cert-manager', '-n', 'cert-manager'],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode == 0:
                        print(f"{Colors.OKGREEN}  ✓ cert-manager uninstalled{Colors.ENDC}")
                    else:
                        print(f"{Colors.FAIL}  ✗ Failed to uninstall cert-manager{Colors.ENDC}")
                        print(f"  {result.stderr}")
                else:
                    print(f"{Colors.OKCYAN}  cert-manager Helm release not found{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}  Error checking cert-manager release: {e}{Colors.ENDC}")

        return success

    def phase2_kubernetes_resources(self) -> bool:
        """Phase 2: Clean Kubernetes resources"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}🧹 PHASE 2: Cleaning Kubernetes Resources{Colors.ENDC}")
        print("=" * 60)

        # Check if cluster is accessible
        try:
            result = subprocess.run(
                ['kubectl', 'cluster-info'],
                capture_output=True,
                timeout=10
            )
            if result.returncode != 0:
                print(f"{Colors.WARNING}⚠  Cluster not accessible, skipping Kubernetes cleanup{Colors.ENDC}")
                return True
        except Exception:
            print(f"{Colors.WARNING}⚠  Cannot verify cluster access, skipping Kubernetes cleanup{Colors.ENDC}")
            return True

        # Delete PVCs
        print(f"\n{Colors.OKCYAN}Deleting PersistentVolumeClaims...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['kubectl', 'get', 'namespace', self.config.n8n_namespace],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                result = subprocess.run(
                    ['kubectl', 'delete', 'pvc', '--all', '-n', self.config.n8n_namespace, '--timeout=60s'],
                    capture_output=True,
                    text=True,
                    timeout=70
                )
                if result.returncode == 0:
                    print(f"{Colors.OKGREEN}  ✓ PVCs deleted{Colors.ENDC}")
                else:
                    print(f"{Colors.OKCYAN}  No PVCs found or already deleted{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}  Error deleting PVCs: {e}{Colors.ENDC}")

        # Delete secrets
        print(f"\n{Colors.OKCYAN}Deleting manual secrets...{Colors.ENDC}")
        for secret_name in ['n8n-basic-auth', 'n8n-tls', 'n8n-db-credentials']:
            try:
                subprocess.run(
                    ['kubectl', 'delete', 'secret', secret_name, '-n', self.config.n8n_namespace],
                    capture_output=True,
                    timeout=10
                )
            except Exception:
                pass
        print(f"{Colors.OKGREEN}  ✓ Secrets cleanup complete{Colors.ENDC}")

        # Delete namespaces
        print(f"\n{Colors.OKCYAN}Deleting namespaces...{Colors.ENDC}")
        for namespace in [self.config.n8n_namespace, 'ingress-nginx', 'cert-manager']:
            try:
                result = subprocess.run(
                    ['kubectl', 'get', 'namespace', namespace],
                    capture_output=True,
                    timeout=10
                )
                if result.returncode == 0:
                    print(f"{Colors.OKCYAN}  Deleting namespace: {namespace}...{Colors.ENDC}")
                    result = subprocess.run(
                        ['kubectl', 'delete', 'namespace', namespace, '--timeout=120s'],
                        capture_output=True,
                        text=True,
                        timeout=130
                    )
                    if result.returncode == 0:
                        print(f"{Colors.OKGREEN}    ✓ {namespace} deleted{Colors.ENDC}")
                    else:
                        print(f"{Colors.WARNING}    ⚠ {namespace} deletion timeout or error{Colors.ENDC}")
            except Exception as e:
                print(f"{Colors.WARNING}  Error with namespace {namespace}: {e}{Colors.ENDC}")

        return True

    def phase3_terraform_destroy(self) -> bool:
        """Phase 3: Destroy Terraform infrastructure"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}💥 PHASE 3: Destroying Terraform Infrastructure{Colors.ENDC}")
        print("=" * 60)

        tfstate_path = self.terraform_dir / "terraform.tfstate"
        if not tfstate_path.exists():
            print(f"{Colors.WARNING}⚠  No Terraform state found, skipping infrastructure destruction{Colors.ENDC}")
            print(f"{Colors.WARNING}  If resources exist in AWS, manually run: cd terraform && terraform destroy{Colors.ENDC}")
            return True

        # Detect AWS region
        aws_region = self.config.aws_region or "us-east-1"

        # Check for RDS deletion protection
        print(f"\n{Colors.OKCYAN}Checking for RDS deletion protection...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['terraform', '-chdir=' + str(self.terraform_dir), 'state', 'list'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0 and 'aws_db_instance' in result.stdout:
                print(f"{Colors.OKCYAN}  RDS instance detected, checking deletion protection...{Colors.ENDC}")

                # Get RDS instance ID from state
                rds_resources = [line for line in result.stdout.split('\n') if 'aws_db_instance' in line]
                if rds_resources:
                    rds_resource = rds_resources[0]

                    # Show the RDS resource details
                    result = subprocess.run(
                        ['terraform', '-chdir=' + str(self.terraform_dir), 'state', 'show', rds_resource],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    if result.returncode == 0:
                        # Extract RDS ID from the output
                        for line in result.stdout.split('\n'):
                            if 'identifier ' in line and '=' in line:
                                rds_id = line.split('=')[1].strip().strip('"')

                                # Check deletion protection via AWS CLI
                                try:
                                    check_result = subprocess.run(
                                        ['aws', 'rds', 'describe-db-instances',
                                         '--db-instance-identifier', rds_id,
                                         '--region', aws_region,
                                         '--query', 'DBInstances[0].DeletionProtection',
                                         '--output', 'text'],
                                        capture_output=True,
                                        text=True,
                                        timeout=30,
                                        env={**os.environ, 'AWS_PROFILE': self.config.aws_profile}
                                    )

                                    if check_result.returncode == 0 and check_result.stdout.strip().upper() == 'TRUE':
                                        print(f"{Colors.WARNING}  ⚠ RDS deletion protection is enabled{Colors.ENDC}")
                                        print(f"{Colors.OKCYAN}  Disabling deletion protection...{Colors.ENDC}")

                                        mod_result = subprocess.run(
                                            ['aws', 'rds', 'modify-db-instance',
                                             '--db-instance-identifier', rds_id,
                                             '--no-deletion-protection',
                                             '--apply-immediately',
                                             '--region', aws_region],
                                            capture_output=True,
                                            text=True,
                                            timeout=30,
                                            env={**os.environ, 'AWS_PROFILE': self.config.aws_profile}
                                        )

                                        if mod_result.returncode == 0:
                                            print(f"{Colors.OKGREEN}    ✓ Deletion protection disabled{Colors.ENDC}")
                                            import time
                                            time.sleep(10)
                                        else:
                                            print(f"{Colors.WARNING}    ⚠ Could not disable deletion protection{Colors.ENDC}")
                                except Exception as e:
                                    print(f"{Colors.WARNING}  Could not check/disable deletion protection: {e}{Colors.ENDC}")
                                break
        except Exception as e:
            print(f"{Colors.WARNING}  Error checking RDS: {e}{Colors.ENDC}")

        # Run terraform destroy
        print(f"\n{Colors.WARNING}{Colors.BOLD}⚠️  Running Terraform Destroy{Colors.ENDC}")
        print(f"{Colors.WARNING}This will permanently delete all infrastructure resources!{Colors.ENDC}\n")

        try:
            result = subprocess.run(
                ['terraform', '-chdir=' + str(self.terraform_dir), 'destroy'],
                timeout=1800  # 30 minutes timeout
            )

            if result.returncode == 0:
                print(f"\n{Colors.OKGREEN}✓ Terraform infrastructure destroyed{Colors.ENDC}")
                return True
            else:
                print(f"\n{Colors.FAIL}✗ Terraform destroy failed{Colors.ENDC}")
                return False
        except subprocess.TimeoutExpired:
            print(f"\n{Colors.FAIL}✗ Terraform destroy timed out{Colors.ENDC}")
            return False
        except Exception as e:
            print(f"\n{Colors.FAIL}✗ Error running terraform destroy: {e}{Colors.ENDC}")
            return False

    def phase4_secrets_manager(self) -> bool:
        """Phase 4: Clean AWS Secrets Manager"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}🔐 PHASE 4: Cleaning AWS Secrets Manager{Colors.ENDC}")
        print("=" * 60)

        aws_region = self.config.aws_region or "us-east-1"

        print(f"\n{Colors.OKCYAN}Searching for n8n-related secrets...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['aws', 'secretsmanager', 'list-secrets',
                 '--region', aws_region,
                 '--query', 'SecretList[?contains(Name, `n8n`)].Name',
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, 'AWS_PROFILE': self.config.aws_profile}
            )

            if result.returncode == 0:
                secrets = json.loads(result.stdout) if result.stdout.strip() else []

                if not secrets:
                    print(f"{Colors.OKCYAN}  No n8n-related secrets found{Colors.ENDC}")
                else:
                    print(f"{Colors.OKCYAN}  Found {len(secrets)} secret(s):{Colors.ENDC}")
                    for secret in secrets:
                        print(f"    - {secret}")

                    prompt = ConfigurationPrompt()
                    if prompt.prompt_yes_no("\nDelete these secrets from AWS Secrets Manager?", default=True):
                        for secret in secrets:
                            print(f"{Colors.OKCYAN}  Deleting: {secret}...{Colors.ENDC}")
                            try:
                                del_result = subprocess.run(
                                    ['aws', 'secretsmanager', 'delete-secret',
                                     '--secret-id', secret,
                                     '--region', aws_region,
                                     '--force-delete-without-recovery'],
                                    capture_output=True,
                                    text=True,
                                    timeout=30,
                                    env={**os.environ, 'AWS_PROFILE': self.config.aws_profile}
                                )

                                if del_result.returncode == 0:
                                    print(f"{Colors.OKGREEN}    ✓ Deleted: {secret}{Colors.ENDC}")
                                else:
                                    print(f"{Colors.WARNING}    ⚠ Failed to delete: {secret}{Colors.ENDC}")
                            except Exception as e:
                                print(f"{Colors.WARNING}    ⚠ Error deleting {secret}: {e}{Colors.ENDC}")
                    else:
                        print(f"{Colors.OKCYAN}  Skipping Secrets Manager cleanup{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}  Could not list secrets: {result.stderr}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}  Error checking Secrets Manager: {e}{Colors.ENDC}")

        return True

    def run(self) -> bool:
        """Run complete teardown sequence"""
        print(f"\n{Colors.RED}{Colors.BOLD}")
        print("╔" + "═" * 58 + "╗")
        print("║" + " " * 58 + "║")
        print("║" + "     N8N EKS DEPLOYMENT TEARDOWN".center(58) + "║")
        print("║" + " " * 58 + "║")
        print("║" + "  This will PERMANENTLY DELETE all resources including:".ljust(59) + "║")
        print("║" + "  • Kubernetes applications (n8n, ingress-nginx)".ljust(59) + "║")
        print("║" + "  • EKS cluster and node groups".ljust(59) + "║")
        print("║" + "  • RDS PostgreSQL database (if exists)".ljust(59) + "║")
        print("║" + "  • VPC, subnets, NAT gateways with Elastic IPs".ljust(59) + "║")
        print("║" + "  • IAM roles and policies".ljust(59) + "║")
        print("║" + "  • SSM parameters and Secrets Manager secrets".ljust(59) + "║")
        print("║" + " " * 58 + "║")
        print("║" + "  ⚠️  THIS CANNOT BE UNDONE! ⚠️".center(62) + "║")
        print("║" + " " * 58 + "║")
        print("╚" + "═" * 58 + "╝")
        print(Colors.ENDC)

        prompt = ConfigurationPrompt()
        if not prompt.prompt_yes_no("\n⚠️  Are you ABSOLUTELY SURE you want to proceed with the teardown?", default=False):
            print(f"\n{Colors.OKCYAN}Teardown cancelled{Colors.ENDC}")
            return False

        print(f"\n{Colors.RED}{Colors.BOLD}Starting teardown in 5 seconds... Press Ctrl+C to cancel{Colors.ENDC}")
        import time
        try:
            for i in range(5, 0, -1):
                print(f"{i}...")
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n{Colors.OKCYAN}Teardown cancelled{Colors.ENDC}")
            return False

        start_time = time.time()

        # Execute teardown phases
        success = True
        success = self.phase1_helm_releases() and success
        success = self.phase2_kubernetes_resources() and success
        success = self.phase3_terraform_destroy() and success
        success = self.phase4_secrets_manager() and success

        end_time = time.time()
        duration = int(end_time - start_time)
        minutes = duration // 60
        seconds = duration % 60

        # Summary
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'═' * 60}{Colors.ENDC}")
        if success:
            print(f"{Colors.OKGREEN}{Colors.BOLD}  ✅ TEARDOWN COMPLETE!{Colors.ENDC}")
        else:
            print(f"{Colors.WARNING}{Colors.BOLD}  ⚠️  TEARDOWN COMPLETED WITH WARNINGS{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'═' * 60}{Colors.ENDC}")
        print(f"\nTotal time: {minutes}m {seconds}s")

        print(f"\n{Colors.BOLD}Next Steps:{Colors.ENDC}")
        print(f"  • Verify DNS records are removed (if you created any)")
        print(f"  • Clean local files: {Colors.OKCYAN}rm -f terraform/aws/terraform.tfstate* terraform/aws/tfplan terraform/aws/terraform.tfvars{Colors.ENDC}")
        print(f"  • Remove kubectl context: {Colors.OKCYAN}kubectl config delete-context $(kubectl config current-context){Colors.ENDC}")
        print(f"\n{Colors.OKGREEN}To deploy again, run: {Colors.OKCYAN}python3 setup.py{Colors.ENDC}\n")

        return success


########################################
# Azure Teardown Class
########################################

class AKSTeardown:
    """Handles teardown of N8N AKS deployment"""

    def __init__(self, script_dir: Path, config: AzureDeploymentConfig):
        self.script_dir = script_dir
        self.config = config
        self.terraform_dir = script_dir / "terraform" / "azure"

    def phase1_helm_releases(self) -> bool:
        """Phase 1: Uninstall Helm releases"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}📦 PHASE 1: Uninstalling Helm Releases{Colors.ENDC}")
        print("=" * 60)

        # Check if cluster is accessible
        try:
            result = subprocess.run(
                ['kubectl', 'cluster-info'],
                capture_output=True,
                timeout=10
            )
            if result.returncode != 0:
                print(f"{Colors.WARNING}⚠  Cluster not accessible, skipping Helm cleanup{Colors.ENDC}")
                print(f"{Colors.WARNING}  If cluster still exists, manually uninstall: helm uninstall n8n -n {self.config.n8n_namespace}{Colors.ENDC}")
                return True
        except Exception as e:
            print(f"{Colors.WARNING}⚠  Cannot verify cluster access: {e}{Colors.ENDC}")
            return True

        success = True

        # Uninstall n8n
        print(f"\n{Colors.OKCYAN}Checking for n8n Helm release...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['helm', 'list', '-n', self.config.n8n_namespace, '-o', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                releases = json.loads(result.stdout) if result.stdout.strip() else []
                n8n_found = any(r.get('name') == 'n8n' for r in releases)

                if n8n_found:
                    print(f"{Colors.OKCYAN}  Uninstalling n8n...{Colors.ENDC}")
                    result = subprocess.run(
                        ['helm', 'uninstall', 'n8n', '-n', self.config.n8n_namespace],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode == 0:
                        print(f"{Colors.OKGREEN}  ✓ n8n uninstalled{Colors.ENDC}")
                    else:
                        print(f"{Colors.FAIL}  ✗ Failed to uninstall n8n{Colors.ENDC}")
                        print(f"  {result.stderr}")
                        success = False
                else:
                    print(f"{Colors.OKCYAN}  n8n Helm release not found{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}  Error checking n8n release: {e}{Colors.ENDC}")
            success = False

        # Uninstall ingress-nginx
        print(f"\n{Colors.OKCYAN}Checking for ingress-nginx Helm release...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['helm', 'list', '-n', 'ingress-nginx', '-o', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                releases = json.loads(result.stdout) if result.stdout.strip() else []
                nginx_found = any(r.get('name') == 'ingress-nginx' for r in releases)

                if nginx_found:
                    print(f"{Colors.OKCYAN}  Uninstalling ingress-nginx...{Colors.ENDC}")
                    result = subprocess.run(
                        ['helm', 'uninstall', 'ingress-nginx', '-n', 'ingress-nginx'],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode == 0:
                        print(f"{Colors.OKGREEN}  ✓ ingress-nginx uninstalled{Colors.ENDC}")
                        print(f"{Colors.OKCYAN}  Waiting for LoadBalancer to be deleted...{Colors.ENDC}")
                        import time
                        time.sleep(30)
                    else:
                        print(f"{Colors.FAIL}  ✗ Failed to uninstall ingress-nginx{Colors.ENDC}")
                        print(f"  {result.stderr}")
                        success = False
                else:
                    print(f"{Colors.OKCYAN}  ingress-nginx Helm release not found{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}  Error checking ingress-nginx release: {e}{Colors.ENDC}")
            success = False

        if success:
            print(f"\n{Colors.OKGREEN}✓ Helm releases cleanup completed{Colors.ENDC}")
        else:
            print(f"\n{Colors.WARNING}⚠  Helm releases cleanup completed with warnings{Colors.ENDC}")

        return success

    def phase2_kubernetes_resources(self) -> bool:
        """Phase 2: Remove Kubernetes resources"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}☸️  PHASE 2: Removing Kubernetes Resources{Colors.ENDC}")
        print("=" * 60)

        # Check cluster access
        try:
            result = subprocess.run(['kubectl', 'cluster-info'], capture_output=True, timeout=10)
            if result.returncode != 0:
                print(f"{Colors.WARNING}⚠  Cluster not accessible, skipping Kubernetes cleanup{Colors.ENDC}")
                return True
        except Exception:
            print(f"{Colors.WARNING}⚠  Cluster not accessible, skipping Kubernetes cleanup{Colors.ENDC}")
            return True

        success = True

        # Delete namespace (this will delete all resources in it)
        print(f"\n{Colors.OKCYAN}Deleting namespace {self.config.n8n_namespace}...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['kubectl', 'delete', 'namespace', self.config.n8n_namespace, '--ignore-not-found=true'],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                print(f"{Colors.OKGREEN}  ✓ Namespace {self.config.n8n_namespace} deleted{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}  ⚠  Failed to delete namespace: {result.stderr}{Colors.ENDC}")
                success = False
        except Exception as e:
            print(f"{Colors.WARNING}  ⚠  Error deleting namespace: {e}{Colors.ENDC}")
            success = False

        # Delete ingress-nginx namespace
        print(f"\n{Colors.OKCYAN}Deleting namespace ingress-nginx...{Colors.ENDC}")
        try:
            result = subprocess.run(
                ['kubectl', 'delete', 'namespace', 'ingress-nginx', '--ignore-not-found=true'],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                print(f"{Colors.OKGREEN}  ✓ Namespace ingress-nginx deleted{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}  ⚠  Failed to delete namespace: {result.stderr}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}  ⚠  Error deleting namespace: {e}{Colors.ENDC}")

        if success:
            print(f"\n{Colors.OKGREEN}✓ Kubernetes resources cleanup completed{Colors.ENDC}")
        else:
            print(f"\n{Colors.WARNING}⚠  Kubernetes resources cleanup completed with warnings{Colors.ENDC}")

        return success

    def phase3_terraform_destroy(self) -> bool:
        """Phase 3: Destroy Azure infrastructure"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}🏗️  PHASE 3: Destroying Azure Infrastructure{Colors.ENDC}")
        print("=" * 60)

        if not self.terraform_dir.exists():
            print(f"{Colors.WARNING}⚠  Terraform directory not found: {self.terraform_dir}{Colors.ENDC}")
            return True

        # Run terraform destroy
        print(f"\n{Colors.HEADER}Running Terraform destroy...{Colors.ENDC}")
        print(f"{Colors.WARNING}This will delete all Azure infrastructure resources{Colors.ENDC}\n")

        result = subprocess.run(
            ['terraform', 'destroy', '-auto-approve'],
            cwd=self.terraform_dir
        )

        if result.returncode == 0:
            print(f"\n{Colors.OKGREEN}✓ Azure infrastructure destroyed{Colors.ENDC}")
            return True
        else:
            print(f"\n{Colors.FAIL}✗ Terraform destroy failed{Colors.ENDC}")
            print(f"{Colors.WARNING}You may need to manually destroy resources in Azure Portal{Colors.ENDC}")
            return False

    def phase4_keyvault_cleanup(self) -> bool:
        """Phase 4: Clean up Azure Key Vault soft-deleted items"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}🔑 PHASE 4: Key Vault Cleanup{Colors.ENDC}")
        print("=" * 60)

        # Azure Key Vault has soft-delete enabled by default
        # We may need to purge soft-deleted vaults
        print(f"\n{Colors.OKCYAN}Checking for soft-deleted Key Vaults...{Colors.ENDC}")

        try:
            # List soft-deleted vaults
            result = subprocess.run(
                ['az', 'keyvault', 'list-deleted', '--query', '[].name', '-o', 'tsv'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0 and result.stdout.strip():
                deleted_vaults = result.stdout.strip().split('\n')
                print(f"{Colors.OKCYAN}  Found {len(deleted_vaults)} soft-deleted Key Vault(s){Colors.ENDC}")

                # Check if any match our resource group pattern
                for vault_name in deleted_vaults:
                    if self.config.resource_group_name.replace('-', '') in vault_name:
                        print(f"\n{Colors.WARNING}⚠  Soft-deleted Key Vault found: {vault_name}{Colors.ENDC}")
                        print(f"{Colors.WARNING}  To permanently delete, run:{Colors.ENDC}")
                        print(f"  {Colors.OKCYAN}az keyvault purge --name {vault_name}{Colors.ENDC}")
            else:
                print(f"{Colors.OKGREEN}  ✓ No soft-deleted Key Vaults found{Colors.ENDC}")

        except Exception as e:
            print(f"{Colors.WARNING}  ⚠  Could not check for soft-deleted vaults: {e}{Colors.ENDC}")

        print(f"\n{Colors.OKGREEN}✓ Key Vault cleanup check completed{Colors.ENDC}")
        return True

    def execute(self) -> bool:
        """Execute full teardown with confirmation"""
        # Display warning banner
        print(f"\n{Colors.RED}{Colors.BOLD}")
        print("╔" + "═" * 58 + "╗")
        print("║" + " " * 58 + "║")
        print("║" + "     N8N AKS DEPLOYMENT TEARDOWN".center(58) + "║")
        print("║" + " " * 58 + "║")
        print("║" + "  This will PERMANENTLY DELETE all resources including:".ljust(59) + "║")
        print("║" + "  • Kubernetes applications (n8n, ingress-nginx)".ljust(59) + "║")
        print("║" + "  • AKS cluster and node pools".ljust(59) + "║")
        print("║" + "  • PostgreSQL Flexible Server (if exists)".ljust(59) + "║")
        print("║" + "  • VNet, subnets, NAT gateways, Public IPs".ljust(59) + "║")
        print("║" + "  • Azure Key Vault and secrets".ljust(59) + "║")
        print("║" + "  • Network Security Groups".ljust(59) + "║")
        print("║" + " " * 58 + "║")
        print("║" + "  ⚠️  THIS CANNOT BE UNDONE! ⚠️".center(62) + "║")
        print("║" + " " * 58 + "║")
        print("╚" + "═" * 58 + "╝")
        print(Colors.ENDC)

        prompt = ConfigurationPrompt()
        if not prompt.prompt_yes_no("\n⚠️  Are you ABSOLUTELY SURE you want to proceed with the teardown?", default=False):
            print(f"\n{Colors.OKCYAN}Teardown cancelled{Colors.ENDC}")
            return False

        print(f"\n{Colors.RED}{Colors.BOLD}Starting teardown in 5 seconds... Press Ctrl+C to cancel{Colors.ENDC}")
        import time
        try:
            for i in range(5, 0, -1):
                print(f"{i}...")
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n{Colors.OKCYAN}Teardown cancelled{Colors.ENDC}")
            return False

        start_time = time.time()

        # Execute teardown phases
        success = True
        success = self.phase1_helm_releases() and success
        success = self.phase2_kubernetes_resources() and success
        success = self.phase3_terraform_destroy() and success
        success = self.phase4_keyvault_cleanup() and success

        end_time = time.time()
        duration = int(end_time - start_time)
        minutes = duration // 60
        seconds = duration % 60

        # Summary
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'═' * 60}{Colors.ENDC}")
        if success:
            print(f"{Colors.OKGREEN}{Colors.BOLD}  ✅ TEARDOWN COMPLETE!{Colors.ENDC}")
        else:
            print(f"{Colors.WARNING}{Colors.BOLD}  ⚠️  TEARDOWN COMPLETED WITH WARNINGS{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'═' * 60}{Colors.ENDC}")
        print(f"\nTotal time: {minutes}m {seconds}s")

        print(f"\n{Colors.BOLD}Next Steps:{Colors.ENDC}")
        print(f"  • Verify resources deleted in Azure Portal")
        print(f"  • Check for soft-deleted Key Vaults: {Colors.OKCYAN}az keyvault list-deleted{Colors.ENDC}")
        print(f"  • Clean local files: {Colors.OKCYAN}rm -f terraform/azure/terraform.tfstate* terraform/azure/tfplan terraform/azure/terraform.tfvars{Colors.ENDC}")
        print(f"  • Remove kubectl context: {Colors.OKCYAN}kubectl config delete-context $(kubectl config current-context){Colors.ENDC}")
        print(f"\n{Colors.OKGREEN}To deploy again, run: {Colors.OKCYAN}python3 setup.py --cloud-provider azure{Colors.ENDC}\n")

        return success


########################################
# Azure Deployment Functions
########################################

def deploy_azure_terraform(config: AzureDeploymentConfig, terraform_dir: Path) -> bool:
    """Deploy Azure infrastructure with Terraform

    Args:
        config: Azure deployment configuration
        terraform_dir: Path to Azure Terraform directory

    Returns:
        bool: True if deployment succeeded
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}🏗️  PHASE 1: Terraform Infrastructure Deployment{Colors.ENDC}")
    print("=" * 60)

    # Initialize Terraform using TerraformRunner
    tf_runner = TerraformRunner(terraform_dir)

    # Initialize
    print(f"\n{Colors.HEADER}Initializing Terraform...{Colors.ENDC}")
    if not tf_runner.init():
        print(f"{Colors.FAIL}✗ Terraform init failed{Colors.ENDC}")
        return False

    # Plan
    print(f"\n{Colors.HEADER}Planning infrastructure...{Colors.ENDC}")
    success, output = tf_runner.plan(display_output=False)
    if not success:
        print(f"{Colors.FAIL}✗ Terraform plan failed{Colors.ENDC}")
        print(output)
        return False

    # Show plan summary
    print(f"{Colors.OKGREEN}✓ Terraform plan completed{Colors.ENDC}")
    print(f"\n{Colors.BOLD}Plan Summary:{Colors.ENDC}")
    print("=" * 60)
    print(output)
    print("=" * 60)

    # Save current state before applying (to preserve previous location's state)
    print(f"\n{Colors.HEADER}💾 Saving current state before deployment...{Colors.ENDC}")
    tfstate_path = terraform_dir / "terraform.tfstate"
    if tfstate_path.exists():
        try:
            with open(tfstate_path, 'r') as f:
                existing_state = json.load(f)
                if existing_state.get('resources'):
                    # Try to detect location from existing state
                    existing_location = None
                    for resource in existing_state.get('resources', []):
                        if resource.get('type') == 'azurerm_kubernetes_cluster':
                            instances = resource.get('instances', [])
                            if instances:
                                location = instances[0].get('attributes', {}).get('location', '')
                                if location:
                                    existing_location = location
                                    break

                    if existing_location:
                        save_state_for_region(terraform_dir, existing_location)
                    else:
                        print(f"{Colors.OKCYAN}  Could not detect location from existing state, using timestamp backup{Colors.ENDC}")
                        timestamp = int(time.time())
                        backup_path = terraform_dir / f"terraform.tfstate.{timestamp}.backup"
                        shutil.copy2(tfstate_path, backup_path)
                        print(f"{Colors.OKGREEN}✓ Saved current state to {backup_path.name}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}⚠  Could not save existing state: {e}{Colors.ENDC}")

    # Apply
    print(f"\n{Colors.HEADER}Deploying infrastructure (this may take 10-15 minutes)...{Colors.ENDC}")
    print(f"{Colors.WARNING}This will create real Azure resources and may incur costs.{Colors.ENDC}\n")

    if not tf_runner.apply():
        print(f"{Colors.FAIL}✗ Terraform apply failed{Colors.ENDC}")
        return False

    print(f"{Colors.OKGREEN}✓ Azure infrastructure deployed{Colors.ENDC}")

    # Save newly created state with location name
    print(f"\n{Colors.HEADER}💾 Saving state for location {config.azure_location}...{Colors.ENDC}")
    save_state_for_region(terraform_dir, config.azure_location)

    # Get kubeconfig
    print(f"\n{Colors.HEADER}Configuring kubectl...{Colors.ENDC}")
    result = subprocess.run([
        'az', 'aks', 'get-credentials',
        '--resource-group', config.resource_group_name,
        '--name', config.cluster_name,
        '--overwrite-existing'
    ], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"{Colors.OKGREEN}✓ kubectl configured for AKS cluster{Colors.ENDC}")
    else:
        print(f"{Colors.FAIL}✗ Failed to configure kubectl{Colors.ENDC}")
        print(result.stderr)
        return False

    # Verify cluster access
    result = subprocess.run(['kubectl', 'cluster-info'], capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        print(f"{Colors.OKGREEN}✓ Cluster accessible{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}⚠  Cluster info check failed, but continuing...{Colors.ENDC}")

    return True


def deploy_azure_helm(config: AzureDeploymentConfig, charts_dir: Path, encryption_key: str) -> bool:
    """Deploy n8n to Azure AKS via Helm

    Args:
        config: Azure deployment configuration
        charts_dir: Path to Helm charts directory
        encryption_key: n8n encryption key

    Returns:
        bool: True if deployment succeeded
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}🚀 PHASE 2: Helm Application Deployment{Colors.ENDC}")
    print("=" * 60)

    # Get LoadBalancer IP from Azure (if available from Terraform outputs)
    print(f"\n{Colors.HEADER}Checking for LoadBalancer IP...{Colors.ENDC}")
    loadbalancer_ip = None

    # Try to get from terraform outputs first
    try:
        terraform_dir = charts_dir.parent / "terraform" / "azure"
        tf_runner = TerraformRunner(terraform_dir)
        outputs = tf_runner.get_outputs()
        loadbalancer_ip = outputs.get('loadbalancer_ip', None)
        if loadbalancer_ip:
            print(f"{Colors.OKGREEN}✓ LoadBalancer IP from Terraform: {loadbalancer_ip}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.OKCYAN}  Could not get LoadBalancer IP from Terraform: {e}{Colors.ENDC}")

    # Prepare Helm values
    helm_values = {
        'image.tag': 'latest',
        'ingress.enabled': str(config.enable_nginx_ingress).lower(),
        'ingress.className': 'nginx',
        'ingress.host': config.n8n_host,
        'ingress.allowLoadBalancerHostname': 'true',
        'ingress.tls.enabled': str(config.enable_cert_manager).lower(),
        'persistence.enabled': 'true',
        'persistence.size': config.n8n_persistence_size,
        'persistence.storageClass': 'managed-csi',
        'env.N8N_HOST': config.n8n_host,
        'env.N8N_PROTOCOL': config.n8n_protocol,
        'env.GENERIC_TIMEZONE': config.timezone,
        'env.TZ': config.timezone,
    }

    # Build helm command
    helm_cmd = [
        'helm', 'upgrade', '--install', 'n8n',
        str(charts_dir / 'n8n'),
        '--namespace', config.n8n_namespace,
        '--create-namespace',
        '--set-string', f'envSecrets.N8N_ENCRYPTION_KEY={encryption_key}'
    ]

    # Add other values
    for key, value in helm_values.items():
        helm_cmd.extend(['--set-string', f'{key}={value}'])

    # Check if values-azure.yaml exists
    values_azure = charts_dir / 'n8n' / 'values-azure.yaml'
    if values_azure.exists():
        helm_cmd.extend(['--values', str(values_azure)])
        print(f"{Colors.OKCYAN}  Using values-azure.yaml{Colors.ENDC}")

    # Deploy
    print(f"\n{Colors.HEADER}Deploying n8n via Helm...{Colors.ENDC}")
    result = subprocess.run(helm_cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        print(f"{Colors.FAIL}✗ Helm deployment failed{Colors.ENDC}")
        print(result.stderr)
        return False

    print(f"{Colors.OKGREEN}✓ n8n deployed to Azure AKS{Colors.ENDC}")

    # Wait for deployment to be ready
    print(f"\n{Colors.HEADER}Waiting for n8n pods to be ready...{Colors.ENDC}")
    result = subprocess.run([
        'kubectl', 'wait', '--for=condition=ready',
        'pod', '-l', 'app.kubernetes.io/name=n8n',
        '-n', config.n8n_namespace,
        '--timeout=300s'
    ], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"{Colors.OKGREEN}✓ n8n pods are ready{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}⚠  Pod readiness check timed out, check manually with:{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl get pods -n {config.n8n_namespace}{Colors.ENDC}")

    # Show access information
    print(f"\n{Colors.OKGREEN}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}  ✅ N8N DEPLOYMENT COMPLETE!{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")

    if loadbalancer_ip:
        print(f"\n{Colors.BOLD}Access Information:{Colors.ENDC}")
        print(f"  n8n URL: {Colors.OKCYAN}{config.n8n_protocol}://{config.n8n_host}{Colors.ENDC}")
        print(f"  LoadBalancer IP: {Colors.OKCYAN}{loadbalancer_ip}{Colors.ENDC}")
        print(f"\n{Colors.WARNING}⚠  Configure DNS:{Colors.ENDC} Point {config.n8n_host} to {loadbalancer_ip}")
    else:
        print(f"\n{Colors.BOLD}Get LoadBalancer IP with:{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}kubectl get svc -n ingress-nginx ingress-nginx-controller{Colors.ENDC}")

    print(f"\n{Colors.BOLD}Verify deployment:{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}kubectl get pods -n {config.n8n_namespace}{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}kubectl get svc -n {config.n8n_namespace}{Colors.ENDC}")

    return True


def main():
    """Main execution flow for N8N Multi-Cloud Deployment - 4 Phase Deployment"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='N8N Multi-Cloud Deployment Setup (AWS EKS / Azure AKS)')
    parser.add_argument('--cloud-provider', type=str, choices=['aws', 'azure'],
                       help='Cloud provider to use (aws or azure). If not specified, you will be prompted to choose.')
    parser.add_argument('--configure-tls', action='store_true',
                       help='Configure TLS for existing n8n deployment')
    parser.add_argument('--skip-terraform', action='store_true',
                       help='Skip Terraform infrastructure deployment and start from application deployment (assumes infrastructure already exists)')
    parser.add_argument('--teardown', action='store_true',
                       help='Teardown and destroy all n8n deployment resources')
    parser.add_argument('--restore-region', type=str, metavar='REGION',
                       help='''Restore terraform state for a specific AWS region or Azure location before running operations.

Use this when you need to manage or teardown a cluster in a different region/location than the current state.

EXAMPLES:
  # AWS: Restore and teardown a cluster in us-west-1
  python setup.py --cloud aws --restore-region us-west-1 --teardown

  # Azure: Restore and teardown a cluster in eastus
  python setup.py --cloud azure --restore-region eastus --teardown

  # Restore state to manage cluster manually
  python setup.py --cloud aws --restore-region us-west-1
  (then run: cd terraform && terraform destroy)

  # List available region/location backups
  ls -lh terraform/aws/terraform.tfstate.*.backup    # AWS
  ls -lh terraform/azure/terraform.tfstate.*.backup  # Azure

WORKFLOW:
  AWS:
    1. Deploy region1 (us-west-1) - state auto-saved to terraform.tfstate.us-west-1.backup
    2. Deploy region2 (us-west-2) - state auto-saved to terraform.tfstate.us-west-2.backup
    3. Restore region1: --cloud aws --restore-region us-west-1
    4. Teardown region1: --cloud aws --restore-region us-west-1 --teardown

  Azure:
    1. Deploy location1 (eastus) - state auto-saved to terraform.tfstate.eastus.backup
    2. Deploy location2 (westus2) - state auto-saved to terraform.tfstate.westus2.backup
    3. Restore location1: --cloud azure --restore-region eastus
    4. Teardown location1: --cloud azure --restore-region eastus --teardown
''')
    args = parser.parse_args()

    script_dir = Path(__file__).parent

    # Determine cloud provider
    cloud_provider = args.cloud_provider
    if not cloud_provider:
        # Prompt user to select cloud provider
        print(f"{Colors.BOLD}{Colors.HEADER}")
        print("=" * 60)
        print("  N8N Multi-Cloud Deployment Setup")
        print("=" * 60)
        print(Colors.ENDC)

        print(f"\n{Colors.HEADER}Select Cloud Provider:{Colors.ENDC}\n")
        print(f"  {Colors.BOLD}1.{Colors.ENDC} AWS (Amazon Web Services) - EKS")
        print(f"  {Colors.BOLD}2.{Colors.ENDC} Azure (Microsoft Azure) - AKS\n")

        prompt = ConfigurationPrompt()
        choice = prompt.prompt_choice("Which cloud provider would you like to use?", ["AWS", "Azure"], default=0)
        cloud_provider = "aws" if choice == "AWS" else "azure"

    # Display banner with selected provider
    provider_name = "AWS EKS" if cloud_provider == "aws" else "Azure AKS"
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("=" * 60)
    print(f"  N8N {provider_name} Deployment Setup")
    print("=" * 60)
    print(Colors.ENDC)

    try:
        # Check dependencies for selected cloud provider
        deps_ok, missing = DependencyChecker.check_all_dependencies(cloud_provider=cloud_provider)
        if not deps_ok:
            sys.exit(1)

        # Handle state restore if --restore-region is specified
        if args.restore_region:
            region_type = "region" if cloud_provider == "aws" else "location"
            print(f"\n{Colors.HEADER}🔄 Restoring Terraform state for {region_type}: {args.restore_region}{Colors.ENDC}")
            print("=" * 60)

            # Determine terraform directory based on cloud provider
            if cloud_provider == "azure":
                terraform_dir = script_dir / "terraform" / "azure"
            else:
                terraform_dir = script_dir / "terraform" / "aws"

            if not restore_state_for_region(terraform_dir, args.restore_region):
                print(f"\n{Colors.FAIL}✗ Failed to restore state for {region_type} {args.restore_region}{Colors.ENDC}")
                sys.exit(1)

            print(f"\n{Colors.OKGREEN}✓ State restored successfully{Colors.ENDC}")

            # If only restoring (no teardown or other operations), exit here
            if not args.teardown and not args.configure_tls and not args.skip_terraform:
                if cloud_provider == "azure":
                    tf_path = "terraform/azure"
                else:
                    tf_path = "terraform/aws"

                print(f"\n{Colors.OKCYAN}State has been restored. You can now run terraform commands manually:{Colors.ENDC}")
                print(f"  cd {tf_path} && terraform plan")
                print(f"  cd {tf_path} && terraform destroy")
                print(f"\n{Colors.OKCYAN}Or run teardown:{Colors.ENDC}")
                print(f"  python setup.py --cloud {cloud_provider} --teardown")
                sys.exit(0)

        # Handle teardown
        if args.teardown:
            # Route to appropriate teardown based on cloud provider
            if cloud_provider == "azure":
                # Azure teardown flow
                config = AzureDeploymentConfig()

                # Try to detect config from Azure terraform.tfvars
                tfvars_path = script_dir / "terraform" / "azure" / "terraform.tfvars"
                if tfvars_path.exists():
                    try:
                        content = tfvars_path.read_text()
                        for line in content.split('\n'):
                            if 'resource_group_name' in line and '=' in line:
                                config.resource_group_name = line.split('=')[1].strip().strip('"')
                            elif 'cluster_name' in line and '=' in line:
                                config.cluster_name = line.split('=')[1].strip().strip('"')
                            elif 'n8n_namespace' in line and '=' in line:
                                config.n8n_namespace = line.split('=')[1].strip().strip('"')
                        print(f"{Colors.OKGREEN}✓ Loaded Azure configuration{Colors.ENDC}")
                    except Exception as e:
                        print(f"{Colors.WARNING}⚠  Could not load Azure config: {e}{Colors.ENDC}")

                # Show detected configuration
                print(f"\n{Colors.HEADER}Azure AKS Teardown Configuration:{Colors.ENDC}")
                print("=" * 60)
                print(f"Resource Group:  {Colors.OKCYAN}{config.resource_group_name}{Colors.ENDC}")
                print(f"Cluster:         {Colors.OKCYAN}{config.cluster_name}{Colors.ENDC}")
                print(f"Namespace:       {Colors.OKCYAN}{config.n8n_namespace}{Colors.ENDC}")
                print("=" * 60)

                teardown = AKSTeardown(script_dir, config)
                success = teardown.execute()
                sys.exit(0 if success else 1)

            else:
                # AWS teardown flow (existing code)
                config = None

                # Try to load from terraform.tfvars first
                try:
                    config = load_existing_configuration(script_dir)
                    print(f"{Colors.OKGREEN}✓ Loaded configuration from terraform.tfvars{Colors.ENDC}")
                except Exception:
                    pass

                # If not found, try to detect from terraform state
                if not config:
                    print(f"\n{Colors.HEADER}Detecting deployment configuration...{Colors.ENDC}")
                    config = DeploymentConfig()

                detected_sources = []

                # Try terraform.tfvars
                tfvars_path = script_dir / "terraform" / "aws" / "terraform.tfvars"
                if tfvars_path.exists():
                    try:
                        content = tfvars_path.read_text()
                        for line in content.split('\n'):
                            if 'aws_profile' in line and '=' in line:
                                config.aws_profile = line.split('=')[1].strip().strip('"')
                            elif 'region' in line and '=' in line:
                                config.aws_region = line.split('=')[1].strip().strip('"')
                                detected_sources.append("terraform.tfvars")
                            elif 'n8n_namespace' in line and '=' in line:
                                config.n8n_namespace = line.split('=')[1].strip().strip('"')
                    except Exception:
                        pass

                # Try terraform.tfstate
                if not config.aws_region:
                    tfstate_path = script_dir / "terraform" / "aws" / "terraform.tfstate"
                    if tfstate_path.exists():
                        try:
                            result = subprocess.run(
                                ['terraform', '-chdir=' + str(script_dir / "terraform" / "aws"), 'output', '-json'],
                                capture_output=True,
                                text=True,
                                timeout=30
                            )
                            if result.returncode == 0:
                                outputs = json.loads(result.stdout)
                                if 'region' in outputs:
                                    config.aws_region = outputs['region'].get('value', '')
                                    detected_sources.append("terraform state")
                        except Exception:
                            pass

                # Try to get from kubectl context (if cluster is accessible)
                if not config.aws_region:
                    try:
                        result = subprocess.run(
                            ['kubectl', 'config', 'current-context'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0 and 'eks' in result.stdout:
                            # Extract region from EKS context (format: arn:aws:eks:REGION:...)
                            context = result.stdout.strip()
                            if 'eks' in context:
                                parts = context.split(':')
                                if len(parts) > 3:
                                    config.aws_region = parts[3]
                                    detected_sources.append("kubectl context")
                    except Exception:
                        pass

                # Show what we found
                if config.aws_region:
                    print(f"{Colors.OKGREEN}✓ Detected region: {config.aws_region} (from {', '.join(detected_sources)}){Colors.ENDC}")

                if config.aws_profile:
                    print(f"{Colors.OKGREEN}✓ Detected AWS profile: {config.aws_profile}{Colors.ENDC}")

            # Prompt for missing critical information
            prompt = ConfigurationPrompt()

            # AWS Profile - ask if not found
            if not config.aws_profile:
                profiles = AWSAuthChecker.get_available_profiles()
                if profiles:
                    print(f"\n{Colors.WARNING}AWS profile not detected{Colors.ENDC}")
                    print(f"Available profiles: {', '.join(profiles)}")
                    config.aws_profile = prompt.prompt(
                        "AWS Profile to use for teardown",
                        default=profiles[0],
                        required=True
                    )
                else:
                    print(f"\n{Colors.WARNING}No AWS profiles found, using 'default'{Colors.ENDC}")
                    config.aws_profile = "default"

            # AWS Region - MUST ask if not found (critical!)
            if not config.aws_region:
                print(f"\n{Colors.WARNING}⚠️  AWS Region not detected from local configuration{Colors.ENDC}")
                common_regions = [
                    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
                    "eu-west-1", "eu-central-1", "ap-southeast-1", "ap-southeast-2"
                ]
                print(f"Common regions: {', '.join(common_regions)}")
                config.aws_region = prompt.prompt(
                    "AWS Region where resources are deployed",
                    default="us-east-1",
                    required=True
                )

            # Namespace - default is fine
            if not config.n8n_namespace:
                config.n8n_namespace = "n8n"

            # Verify AWS credentials
            print(f"\n{Colors.HEADER}🔐 Verifying AWS credentials...{Colors.ENDC}")
            success, message = AWSAuthChecker.verify_credentials(
                config.aws_profile,
                config.aws_region
            )

            if success:
                print(f"{Colors.OKGREEN}✓ AWS credentials verified{Colors.ENDC}")
                print(f"  {message}")
            else:
                print(f"{Colors.FAIL}✗ AWS authentication failed{Colors.ENDC}")
                print(f"  {message}")
                print(f"\n{Colors.WARNING}Please verify your AWS credentials and region are correct{Colors.ENDC}")
                if not prompt.prompt_yes_no("Continue with teardown anyway?", default=False):
                    sys.exit(1)

            # Show final configuration summary
            print(f"\n{Colors.HEADER}{Colors.BOLD}Teardown Configuration{Colors.ENDC}")
            print("=" * 60)
            print(f"AWS Profile:     {Colors.OKCYAN}{config.aws_profile}{Colors.ENDC}")
            print(f"AWS Region:      {Colors.OKCYAN}{config.aws_region}{Colors.ENDC}")
            print(f"Namespace:       {Colors.OKCYAN}{config.n8n_namespace}{Colors.ENDC}")
            print("=" * 60)

            teardown = TeardownRunner(script_dir, config)
            success = teardown.run()
            sys.exit(0 if success else 1)

        if args.configure_tls:
            try:
                config = load_existing_configuration(script_dir, cloud_provider)
            except Exception as e:
                print(f"{Colors.FAIL}✗ Unable to load existing configuration: {e}{Colors.ENDC}")
                print("Run the full deployment once before using --configure-tls.")
                sys.exit(1)

            # Configure kubectl from terraform outputs
            tf_runner = TerraformRunner(script_dir / "terraform" / cloud_provider)
            outputs = tf_runner.get_outputs()

            if outputs and 'configure_kubectl' in outputs:
                print(f"\n{Colors.HEADER}🔧 Configuring kubectl...{Colors.ENDC}")
                kubectl_cmd = outputs['configure_kubectl']
                result = subprocess.run(kubectl_cmd, shell=True, capture_output=True, text=True)

                if result.returncode == 0:
                    print(f"{Colors.OKGREEN}✓ kubectl configured{Colors.ENDC}")
                else:
                    print(f"{Colors.WARNING}⚠  kubectl configuration failed. Run manually:{Colors.ENDC}")
                    print(f"  {Colors.OKCYAN}{kubectl_cmd}{Colors.ENDC}")

            loadbalancer_url = get_loadbalancer_url(max_attempts=30, delay=10)
            if not loadbalancer_url:
                print(f"{Colors.FAIL}✗ Unable to determine LoadBalancer hostname{Colors.ENDC}")
                print("Ensure kubectl is pointed at your cluster and try again.")
                sys.exit(1)

            success = configure_tls_interactive(config, script_dir, loadbalancer_url)
            sys.exit(0 if success else 1)

        if args.skip_terraform:
            # Load existing configuration and skip to Phase 2
            print(f"\n{Colors.WARNING}⚡ Skip-Terraform Mode Enabled{Colors.ENDC}")
            print(f"{Colors.OKCYAN}Assuming infrastructure is already deployed...{Colors.ENDC}\n")

            try:
                config = load_existing_configuration(script_dir, cloud_provider)
                print(f"{Colors.OKGREEN}✓ Loaded configuration from terraform.tfvars{Colors.ENDC}")
            except Exception as e:
                print(f"{Colors.FAIL}✗ Unable to load existing configuration: {e}{Colors.ENDC}")
                print("Run the full deployment once before using --skip-terraform.")
                sys.exit(1)

            tf_runner = TerraformRunner(script_dir / "terraform" / cloud_provider)

            # Verify Terraform state exists
            tfstate_path = script_dir / "terraform" / cloud_provider / "terraform.tfstate"
            if not tfstate_path.exists():
                print(f"{Colors.FAIL}✗ Terraform state not found{Colors.ENDC}")
                print("Infrastructure must be deployed first. Run without --skip-terraform.")
                sys.exit(1)

            print(f"{Colors.OKGREEN}✓ Terraform state found{Colors.ENDC}")

            # Get outputs from existing Terraform state
            print(f"\n{Colors.HEADER}📊 Reading Terraform outputs...{Colors.ENDC}")
            outputs = tf_runner.get_outputs()

            if not outputs:
                print(f"{Colors.FAIL}✗ Unable to read Terraform outputs{Colors.ENDC}")
                print("Ensure Terraform has been applied successfully.")
                sys.exit(1)

            print(f"{Colors.OKGREEN}✓ Retrieved Terraform outputs{Colors.ENDC}")

            # Configure kubectl if needed
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
        else:
            # Route to appropriate deployment based on cloud provider
            if cloud_provider == "azure":
                # ═══════════════════════════════════════════════════════════════
                # AZURE AKS DEPLOYMENT FLOW
                # ═══════════════════════════════════════════════════════════════

                # Collect Azure configuration
                print(f"\n{Colors.HEADER}Let's configure your Azure AKS deployment...{Colors.ENDC}")
                prompt = ConfigurationPrompt(cloud_provider="azure")
                config = prompt.collect_azure_configuration(skip_tls=True)

                # Save configuration to history
                ConfigHistoryManager.save_configuration(config, "azure", script_dir)

                # Create Terraform tfvars
                updater = FileUpdater(script_dir)
                updater.create_terraform_tfvars_azure(config)

                # Deploy Azure infrastructure via Terraform
                terraform_dir = script_dir / "terraform" / "azure"
                if not deploy_azure_terraform(config, terraform_dir):
                    raise Exception("Azure infrastructure deployment failed")

                # Deploy n8n application via Helm
                charts_dir = script_dir / "charts"
                if not deploy_azure_helm(config, charts_dir, config.n8n_encryption_key):
                    raise Exception("Azure n8n deployment failed")

                print(f"\n{Colors.BOLD}Useful Commands:{Colors.ENDC}")
                print(f"  {Colors.OKCYAN}kubectl get pods -n {config.n8n_namespace}{Colors.ENDC}")
                print(f"  {Colors.OKCYAN}kubectl get ingress -n {config.n8n_namespace}{Colors.ENDC}")
                print(f"  {Colors.OKCYAN}kubectl logs -f deployment/n8n -n {config.n8n_namespace}{Colors.ENDC}")
                print(f"  {Colors.OKCYAN}kubectl get svc -n ingress-nginx{Colors.ENDC}")

                print("\n" + "=" * 60)

            else:
                # ═══════════════════════════════════════════════════════════════
                # AWS EKS DEPLOYMENT FLOW (existing code)
                # ═══════════════════════════════════════════════════════════════

                # Collect configuration (skip TLS - will be configured after LoadBalancer is ready)
                print(f"\n{Colors.HEADER}Let's configure your EKS deployment...{Colors.ENDC}")
                prompt = ConfigurationPrompt()
                config = prompt.collect_configuration(skip_tls=True)

                # Save configuration to history
                ConfigHistoryManager.save_configuration(config, "aws", script_dir)

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

            tf_runner = TerraformRunner(script_dir / "terraform" / "aws")

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

            # Save current state before applying (to preserve previous region's state)
            print(f"\n{Colors.HEADER}💾 Saving current state before deployment...{Colors.ENDC}")
            tfstate_path = script_dir / "terraform" / "aws" / "terraform.tfstate"
            if tfstate_path.exists():
                try:
                    with open(tfstate_path, 'r') as f:
                        existing_state = json.load(f)
                        if existing_state.get('resources'):
                            # Try to detect region from existing state
                            existing_region = None
                            for resource in existing_state.get('resources', []):
                                if resource.get('type') == 'aws_eks_cluster':
                                    instances = resource.get('instances', [])
                                    if instances:
                                        arn = instances[0].get('attributes', {}).get('arn', '')
                                        if arn:
                                            # ARN format: arn:aws:eks:REGION:...
                                            existing_region = arn.split(':')[3] if len(arn.split(':')) > 3 else None
                                            break

                            if existing_region:
                                save_state_for_region(script_dir / "terraform" / "aws", existing_region)
                            else:
                                print(f"{Colors.OKCYAN}  Could not detect region from existing state, using timestamp backup{Colors.ENDC}")
                                timestamp = int(time.time())
                                backup_path = script_dir / "terraform" / "aws" / f"terraform.tfstate.{timestamp}.backup"
                                shutil.copy2(tfstate_path, backup_path)
                                print(f"{Colors.OKGREEN}✓ Saved current state to {backup_path.name}{Colors.ENDC}")
                except Exception as e:
                    print(f"{Colors.WARNING}⚠  Could not save existing state: {e}{Colors.ENDC}")

            if not tf_runner.apply():
                raise Exception("Terraform apply failed")

            print(f"\n{Colors.OKGREEN}✓ Infrastructure deployed successfully{Colors.ENDC}")

            # Save newly created state with region name
            print(f"\n{Colors.HEADER}💾 Saving state for region {config.aws_region}...{Colors.ENDC}")
            save_state_for_region(script_dir / "terraform" / "aws", config.aws_region)

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

        helm_runner = HelmRunner(script_dir / "charts" / "n8n")
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

        # Cleanup backup on success (only if updater was created)
        if 'updater' in locals():
            updater.cleanup_backup()

    except SetupInterrupted as e:
        print(f"\n{Colors.WARNING}{e}{Colors.ENDC}")
        if 'updater' in locals():
            updater.restore_backup()
            updater.cleanup_backup()
        sys.exit(1)

    except Exception as e:
        print(f"\n{Colors.FAIL}Error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        if 'updater' in locals():
            updater.restore_backup()
            updater.cleanup_backup()
        sys.exit(1)

if __name__ == "__main__":
    main()
