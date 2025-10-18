#!/usr/bin/env python3
"""
Azure-specific deployment logic for n8n on AKS
"""

import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

from .common import Colors, print_error, print_success, print_info


@dataclass
class AzureConfig:
    """Azure AKS deployment configuration"""
    # Azure Settings
    azure_subscription_id: str
    azure_location: str

    # Resource Group
    resource_group_name: str = "n8n-rg"
    project_tag: str = "n8n-app"

    # VNet Settings
    vnet_cidr: str = "10.0.0.0/16"

    # AKS Cluster Settings
    cluster_name: str = "n8n-aks-cluster"
    kubernetes_version: str = "1.29"

    # Node Pool Settings
    node_vm_size: str = "Standard_D2s_v3"
    node_count: int = 2
    node_min_count: int = 1
    node_max_count: int = 5
    enable_auto_scaling: bool = True

    # Application Settings
    n8n_host: str = ""
    n8n_namespace: str = "n8n"
    n8n_protocol: str = "http"
    n8n_persistence_size: str = "10Gi"
    timezone: str = "America/Bahia"
    n8n_encryption_key: str = ""

    # Database Settings
    database_type: str = "sqlite"  # sqlite or postgresql
    postgres_sku: str = "B_Standard_B1ms"
    postgres_storage_gb: int = 32
    postgres_high_availability: bool = False
    postgres_version: str = "15"

    # Optional Features
    enable_nginx_ingress: bool = True
    enable_basic_auth: bool = False
    enable_cert_manager: bool = False

    # TLS Settings
    tls_certificate_source: str = "none"  # none, byo, or letsencrypt
    letsencrypt_email: str = ""
    letsencrypt_environment: str = "production"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)

    def to_terraform_vars(self) -> Dict[str, Any]:
        """Convert to Terraform variables format"""
        return {
            'azure_subscription_id': self.azure_subscription_id,
            'azure_location': self.azure_location,
            'resource_group_name': self.resource_group_name,
            'project_tag': self.project_tag,
            'vnet_cidr': self.vnet_cidr,
            'cluster_name': self.cluster_name,
            'kubernetes_version': self.kubernetes_version,
            'node_vm_size': self.node_vm_size,
            'node_count': self.node_count,
            'node_min_count': self.node_min_count,
            'node_max_count': self.node_max_count,
            'enable_auto_scaling': self.enable_auto_scaling,
            'n8n_host': self.n8n_host,
            'n8n_namespace': self.n8n_namespace,
            'n8n_protocol': self.n8n_protocol,
            'n8n_persistence_size': self.n8n_persistence_size,
            'timezone': self.timezone,
            'n8n_encryption_key': self.n8n_encryption_key,
            'database_type': self.database_type,
            'postgres_sku': self.postgres_sku,
            'postgres_storage_gb': self.postgres_storage_gb,
            'postgres_high_availability': self.postgres_high_availability,
            'postgres_version': self.postgres_version,
            'enable_nginx_ingress': self.enable_nginx_ingress,
            'enable_basic_auth': self.enable_basic_auth,
            'enable_cert_manager': self.enable_cert_manager,
        }


class AzureAuthValidator:
    """Validates Azure CLI authentication"""

    @staticmethod
    def check_azure_auth() -> bool:
        """Check if Azure CLI is authenticated"""
        try:
            cmd = ['az', 'account', 'show']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                account_info = json.loads(result.stdout)
                subscription_name = account_info.get('name', 'Unknown')
                subscription_id = account_info.get('id', 'Unknown')
                print_success(f"Azure authentication successful")
                print_info(f"Subscription: {subscription_name} ({subscription_id})")
                return True
            else:
                print_error("Azure authentication failed")
                print(f"{Colors.FAIL}Error: {result.stderr.strip()}{Colors.ENDC}")
                print(f"\n{Colors.OKCYAN}To authenticate with Azure, run:{Colors.ENDC}")
                print(f"  az login\n")
                return False

        except subprocess.TimeoutExpired:
            print_error("Azure CLI command timed out")
            return False
        except json.JSONDecodeError:
            print_error("Failed to parse Azure CLI output")
            return False
        except Exception as e:
            print_error(f"Error checking Azure authentication: {e}")
            return False

    @staticmethod
    def get_azure_subscriptions() -> List[Dict[str, str]]:
        """Get list of Azure subscriptions"""
        try:
            cmd = ['az', 'account', 'list', '--output', 'json']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                subscriptions = json.loads(result.stdout)
                return [
                    {
                        'id': sub['id'],
                        'name': sub['name'],
                        'is_default': sub.get('isDefault', False)
                    }
                    for sub in subscriptions
                ]
            return []

        except Exception:
            return []

    @staticmethod
    def set_subscription(subscription_id: str) -> bool:
        """Set active Azure subscription"""
        try:
            cmd = ['az', 'account', 'set', '--subscription', subscription_id]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                print_success(f"Active subscription set to: {subscription_id}")
                return True
            else:
                print_error(f"Failed to set subscription: {result.stderr}")
                return False

        except Exception as e:
            print_error(f"Error setting subscription: {e}")
            return False

    @staticmethod
    def get_azure_locations() -> List[str]:
        """Get list of Azure regions"""
        # Common Azure regions
        return [
            'eastus',          # East US
            'eastus2',         # East US 2
            'westus',          # West US
            'westus2',         # West US 2
            'westus3',         # West US 3
            'centralus',       # Central US
            'northcentralus',  # North Central US
            'southcentralus',  # South Central US
            'westeurope',      # West Europe
            'northeurope',     # North Europe
            'uksouth',         # UK South
            'ukwest',          # UK West
            'francecentral',   # France Central
            'germanywestcentral', # Germany West Central
            'swedencentral',   # Sweden Central
            'norwayeast',      # Norway East
            'switzerlandnorth', # Switzerland North
            'canadacentral',   # Canada Central
            'canadaeast',      # Canada East
            'brazilsouth',     # Brazil South
            'southeastasia',   # Southeast Asia
            'eastasia',        # East Asia
            'australiaeast',   # Australia East
            'australiasoutheast', # Australia Southeast
            'japaneast',       # Japan East
            'japanwest',       # Japan West
            'koreacentral',    # Korea Central
            'southafricanorth', # South Africa North
            'uaenorth',        # UAE North
        ]


class AzureTerraformHelper:
    """Helper for Terraform operations on Azure"""

    def __init__(self, terraform_dir: Path):
        self.terraform_dir = terraform_dir

    def write_tfvars(self, config: AzureConfig) -> bool:
        """Write terraform.tfvars file for Azure"""
        tfvars_path = self.terraform_dir / "terraform.tfvars"

        try:
            with open(tfvars_path, 'w') as f:
                f.write("# Azure AKS Deployment Configuration\n")
                f.write(f"# Generated automatically - do not edit manually\n\n")

                # Azure Configuration
                f.write("# Azure Configuration\n")
                f.write(f'azure_subscription_id = "{config.azure_subscription_id}"\n')
                f.write(f'azure_location = "{config.azure_location}"\n\n')

                # Resource Group
                f.write("# Resource Group\n")
                f.write(f'resource_group_name = "{config.resource_group_name}"\n')
                f.write(f'project_tag = "{config.project_tag}"\n\n')

                # VNet
                f.write("# Virtual Network\n")
                f.write(f'vnet_cidr = "{config.vnet_cidr}"\n\n')

                # AKS Configuration
                f.write("# AKS Cluster Configuration\n")
                f.write(f'cluster_name = "{config.cluster_name}"\n')
                f.write(f'kubernetes_version = "{config.kubernetes_version}"\n\n')

                # Node Pool
                f.write("# Node Pool Configuration\n")
                f.write(f'node_vm_size = "{config.node_vm_size}"\n')
                f.write(f'node_count = {config.node_count}\n')
                f.write(f'node_min_count = {config.node_min_count}\n')
                f.write(f'node_max_count = {config.node_max_count}\n')
                f.write(f'enable_auto_scaling = {str(config.enable_auto_scaling).lower()}\n\n')

                # Application Settings
                f.write("# Application Configuration\n")
                f.write(f'n8n_host = "{config.n8n_host}"\n')
                f.write(f'n8n_namespace = "{config.n8n_namespace}"\n')
                f.write(f'n8n_protocol = "{config.n8n_protocol}"\n')
                f.write(f'n8n_persistence_size = "{config.n8n_persistence_size}"\n')
                f.write(f'timezone = "{config.timezone}"\n')
                if config.n8n_encryption_key:
                    f.write(f'n8n_encryption_key = "{config.n8n_encryption_key}"\n')
                f.write('\n')

                # Database Configuration
                f.write("# Database Configuration\n")
                f.write(f'database_type = "{config.database_type}"\n')
                if config.database_type == "postgresql":
                    f.write(f'postgres_sku = "{config.postgres_sku}"\n')
                    f.write(f'postgres_storage_gb = {config.postgres_storage_gb}\n')
                    f.write(f'postgres_high_availability = {str(config.postgres_high_availability).lower()}\n')
                    f.write(f'postgres_version = "{config.postgres_version}"\n')
                f.write('\n')

                # Optional Features
                f.write("# Optional Features\n")
                f.write(f'enable_nginx_ingress = {str(config.enable_nginx_ingress).lower()}\n')
                f.write(f'enable_basic_auth = {str(config.enable_basic_auth).lower()}\n')
                f.write(f'enable_cert_manager = {str(config.enable_cert_manager).lower()}\n')

            print_success(f"Terraform configuration written to {tfvars_path}")
            return True

        except Exception as e:
            print_error(f"Failed to write terraform.tfvars: {e}")
            return False


def configure_kubectl_for_aks(cluster_name: str, resource_group: str) -> bool:
    """Configure kubectl to use AKS cluster"""
    print_info(f"Configuring kubectl for AKS cluster: {cluster_name}")

    try:
        cmd = [
            'az', 'aks', 'get-credentials',
            '--resource-group', resource_group,
            '--name', cluster_name,
            '--overwrite-existing'
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
