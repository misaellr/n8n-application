#!/usr/bin/env python3
"""
N8N Multi-Cloud Deployment CLI
Unified setup script for deploying n8n on AWS EKS or Azure AKS
"""

import sys
import argparse
from pathlib import Path

# Add lib directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))

from common import (
    Colors, SetupInterrupted, DependencyChecker,
    UserPrompts, print_banner, print_success, print_error, print_info
)


def select_cloud_provider() -> str:
    """Prompt user to select cloud provider"""
    print_banner("Multi-Cloud")

    print(f"\n{Colors.HEADER}Select Cloud Provider{Colors.ENDC}\n")
    choices = [
        "AWS (Amazon EKS)",
        "Azure (AKS)",
    ]

    cloud = UserPrompts.prompt_choice("Which cloud provider would you like to use?", choices, default=0)

    if "AWS" in cloud:
        return "aws"
    elif "Azure" in cloud:
        return "azure"
    else:
        print_error("Invalid cloud provider selected")
        sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="N8N Multi-Cloud Deployment Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive cloud selection
  python3 setup.py

  # Deploy to AWS
  python3 setup.py --cloud aws

  # Deploy to Azure
  python3 setup.py --cloud azure

  # Teardown AWS deployment
  python3 setup.py --cloud aws --teardown

  # Skip Terraform and deploy application only (AWS)
  python3 setup.py --cloud aws --skip-terraform
        """
    )

    parser.add_argument(
        '--cloud',
        choices=['aws', 'azure'],
        help='Cloud provider to use (aws or azure)'
    )

    parser.add_argument(
        '--teardown',
        action='store_true',
        help='Teardown existing deployment'
    )

    parser.add_argument(
        '--skip-terraform',
        action='store_true',
        help='Skip Terraform infrastructure deployment (application only)'
    )

    args = parser.parse_args()

    try:
        # Determine cloud provider
        if args.cloud:
            cloud = args.cloud
            print_banner(cloud.upper())
        else:
            cloud = select_cloud_provider()

        # Check dependencies for selected cloud
        deps_ok, _ = DependencyChecker.check_dependencies(cloud)
        if not deps_ok:
            print_error("Missing dependencies. Please install required tools and try again.")
            sys.exit(1)

        # Route to appropriate cloud deployment
        if cloud == "aws":
            print_info("AWS deployment is currently using the legacy script.")
            print_info("Please use: python3 setup.py for AWS EKS deployment")
            print_info("The unified CLI will be available in a future release.")
            sys.exit(0)

        elif cloud == "azure":
            print_info("Azure deployment infrastructure is being set up.")
            print_info("Azure deployment will be available in the next release.")
            print_info("Infrastructure files will be located in: terraform/azure/")
            sys.exit(0)

    except SetupInterrupted:
        print(f"\n{Colors.WARNING}⚠  Setup interrupted by user{Colors.ENDC}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}⚠  Setup interrupted by user{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
