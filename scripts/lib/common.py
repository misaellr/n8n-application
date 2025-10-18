#!/usr/bin/env python3
"""
Common utilities for multi-cloud n8n deployment
Shared functions and classes for AWS, Azure, and GCP deployments
"""

import os
import sys
import re
import json
import subprocess
import shutil
import secrets
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List


# ANSI color codes
class Colors:
    """Terminal color codes for formatted output"""
    HEADER = '\033[94m'      # Light Blue for headers
    OKBLUE = '\033[1;94m'    # Bold Light Blue for branding elements
    OKCYAN = '\033[96m'      # Cyan for informational text
    OKGREEN = '\033[92m'     # Green for success messages
    WARNING = '\033[93m'     # Yellow for warnings
    FAIL = '\033[91m'        # Red for errors
    RED = '\033[91m'         # Red (alias for compatibility)
    ENDC = '\033[0m'         # Reset color
    BOLD = '\033[1m'         # Bold text
    UNDERLINE = '\033[4m'    # Underlined text


class SetupInterrupted(Exception):
    """Raised when user interrupts the setup process"""
    pass


class DeploymentError(Exception):
    """Raised when deployment encounters an error"""
    pass


class DependencyChecker:
    """Checks for required CLI tools for cloud deployments"""

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
            'version_regex': r'"azure-cli": "([0-9]+\.[0-9]+\.[0-9]+)"',
            'min_version': '2.50.0',
            'install_url': 'https://docs.microsoft.com/en-us/cli/azure/install-azure-cli',
            'description': 'Azure Command Line Interface'
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
    def check_dependencies(cls, cloud: str = "common") -> Tuple[bool, list]:
        """Check required dependencies for specified cloud deployment

        Args:
            cloud: "common", "aws", or "azure"

        Returns:
            Tuple of (success: bool, missing_or_outdated: list)
        """
        missing = []
        outdated = []

        print(f"\n{Colors.HEADER}🔍 Checking dependencies for {cloud.upper()} deployment...{Colors.ENDC}")

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

        # Select tools to check based on cloud
        tools_to_check = cls.COMMON_TOOLS.copy()
        if cloud == "aws":
            tools_to_check.update(cls.AWS_TOOLS)
        elif cloud == "azure":
            tools_to_check.update(cls.AZURE_TOOLS)

        # Check all required tools
        for tool, info in tools_to_check.items():
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

            with open(path, 'r') as f:
                content = f.read()

            # Basic PEM format validation
            if cert_type == "certificate":
                if not ("-----BEGIN CERTIFICATE-----" in content and "-----END CERTIFICATE-----" in content):
                    return False, "Invalid certificate format (missing PEM markers)"
            elif cert_type == "private_key":
                key_markers = ["-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----", "-----BEGIN EC PRIVATE KEY-----"]
                if not any(marker in content for marker in key_markers):
                    return False, "Invalid private key format (missing PEM markers)"

            return True, content

        except Exception as e:
            return False, f"Error reading file: {str(e)}"


class UserPrompts:
    """Common user input and prompt functions"""

    @staticmethod
    def prompt_input(prompt: str, default: str = "") -> str:
        """Prompt user for input with optional default value"""
        if default:
            user_input = input(f"{prompt} [{default}]: ").strip()
            return user_input if user_input else default
        else:
            return input(f"{prompt}: ").strip()

    @staticmethod
    def prompt_yes_no(prompt: str, default: bool = False) -> bool:
        """Prompt user for yes/no confirmation"""
        default_str = "Y/n" if default else "y/N"
        response = input(f"{prompt} [{default_str}]: ").strip().lower()

        if not response:
            return default
        return response in ('y', 'yes')

    @staticmethod
    def prompt_choice(prompt: str, choices: List[str], default: Optional[int] = None) -> str:
        """Prompt user to select from a list of choices

        Args:
            prompt: The question to ask
            choices: List of choice strings
            default: Default choice index (0-based)

        Returns:
            Selected choice string
        """
        print(f"\n{prompt}")
        for i, choice in enumerate(choices, 1):
            default_marker = " (default)" if default is not None and i-1 == default else ""
            print(f"  {i}. {choice}{default_marker}")

        while True:
            try:
                response = input(f"Enter choice [1-{len(choices)}]: ").strip()
                if not response and default is not None:
                    return choices[default]

                index = int(response) - 1
                if 0 <= index < len(choices):
                    return choices[index]
                else:
                    print(f"{Colors.FAIL}Invalid choice. Please enter a number between 1 and {len(choices)}.{Colors.ENDC}")
            except ValueError:
                print(f"{Colors.FAIL}Invalid input. Please enter a number.{Colors.ENDC}")
            except KeyboardInterrupt:
                raise SetupInterrupted()


class KubernetesHelper:
    """Helper functions for Kubernetes operations"""

    @staticmethod
    def run_kubectl(args: List[str], capture_output: bool = True, check: bool = True) -> subprocess.CompletedProcess:
        """Run kubectl command"""
        cmd = ['kubectl'] + args
        return subprocess.run(cmd, capture_output=capture_output, text=True, check=check)

    @staticmethod
    def namespace_exists(namespace: str) -> bool:
        """Check if a Kubernetes namespace exists"""
        try:
            result = KubernetesHelper.run_kubectl(['get', 'namespace', namespace], check=False)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def create_namespace(namespace: str) -> bool:
        """Create a Kubernetes namespace if it doesn't exist"""
        if KubernetesHelper.namespace_exists(namespace):
            return True

        try:
            KubernetesHelper.run_kubectl(['create', 'namespace', namespace])
            print(f"{Colors.OKGREEN}✓ Created namespace: {namespace}{Colors.ENDC}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"{Colors.FAIL}✗ Failed to create namespace: {e}{Colors.ENDC}")
            return False

    @staticmethod
    def wait_for_deployment(deployment: str, namespace: str, timeout: int = 300) -> bool:
        """Wait for a deployment to be ready"""
        print(f"{Colors.OKCYAN}⏳ Waiting for deployment {deployment} to be ready (timeout: {timeout}s)...{Colors.ENDC}")
        try:
            KubernetesHelper.run_kubectl([
                'wait', '--for=condition=available',
                f'deployment/{deployment}',
                f'-n {namespace}',
                f'--timeout={timeout}s'
            ])
            print(f"{Colors.OKGREEN}✓ Deployment {deployment} is ready{Colors.ENDC}")
            return True
        except subprocess.CalledProcessError:
            print(f"{Colors.FAIL}✗ Deployment {deployment} did not become ready within {timeout}s{Colors.ENDC}")
            return False


class HelmHelper:
    """Helper functions for Helm operations"""

    @staticmethod
    def run_helm(args: List[str], capture_output: bool = True, check: bool = True) -> subprocess.CompletedProcess:
        """Run helm command"""
        cmd = ['helm'] + args
        return subprocess.run(cmd, capture_output=capture_output, text=True, check=check)

    @staticmethod
    def release_exists(release: str, namespace: str) -> bool:
        """Check if a Helm release exists"""
        try:
            result = HelmHelper.run_helm(['list', '-n', namespace, '-q'], check=False)
            if result.returncode == 0:
                releases = result.stdout.strip().split('\n')
                return release in releases
            return False
        except Exception:
            return False

    @staticmethod
    def get_release_values(release: str, namespace: str) -> Optional[Dict]:
        """Get values for an existing Helm release"""
        try:
            result = HelmHelper.run_helm(['get', 'values', release, '-n', namespace, '-o', 'json'])
            if result.returncode == 0:
                return json.loads(result.stdout)
            return None
        except Exception:
            return None


def generate_encryption_key(length: int = 64) -> str:
    """Generate a secure random encryption key

    Args:
        length: Length of hex key (default: 64 characters)

    Returns:
        Hexadecimal string of specified length
    """
    return secrets.token_hex(length // 2)


def generate_random_password(length: int = 12) -> str:
    """Generate a secure random password

    Args:
        length: Length of password (default: 12)

    Returns:
        Alphanumeric password string
    """
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def print_banner(cloud: str = "Multi-Cloud"):
    """Print deployment banner"""
    banner = f"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║          N8N {cloud.upper()} DEPLOYMENT AUTOMATION               ║
║                                                          ║
║  Automated deployment of n8n workflow automation         ║
║  platform using Terraform and Helm                       ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""
    print(f"{Colors.OKBLUE}{banner}{Colors.ENDC}")


def print_phase_header(phase: int, title: str):
    """Print phase header"""
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}  📦 PHASE {phase}: {title.upper()}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")


def print_success(message: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")


def print_error(message: str):
    """Print error message"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")


def print_warning(message: str):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠  {message}{Colors.ENDC}")


def print_info(message: str):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ  {message}{Colors.ENDC}")
