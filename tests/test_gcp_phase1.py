#!/usr/bin/env python3
"""
Unit tests for GCP Phase 1 implementation

Tests cover:
- GCPDeploymentConfig class and serialization
- GCPAuthChecker authentication and API verification
- DependencyChecker GCP support
- ConfigHistoryManager GCP integration
- ConfigurationPrompt GCP configuration collection (mocked)

Target: 90%+ code coverage for Phase 1 components
"""

import unittest
import json
import subprocess
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path
import sys
import tempfile
import shutil

# Add parent directory to path to import setup.py modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from setup import (
    GCPDeploymentConfig,
    GCPAuthChecker,
    DependencyChecker,
    ConfigHistoryManager,
    ConfigurationPrompt,
    SetupInterrupted
)


class TestGCPDeploymentConfig(unittest.TestCase):
    """Test GCPDeploymentConfig class"""

    def test_init_defaults(self):
        """Test GCPDeploymentConfig initialization with defaults"""
        config = GCPDeploymentConfig()

        self.assertEqual(config.cloud_provider, "gcp")
        self.assertEqual(config.gcp_project_id, "")
        self.assertEqual(config.gcp_region, "us-central1")
        self.assertEqual(config.gcp_zone, "us-central1-a")
        self.assertEqual(config.cluster_name, "n8n-gke-cluster")
        self.assertEqual(config.node_machine_type, "e2-medium")
        self.assertEqual(config.node_count, 1)
        self.assertEqual(config.vpc_name, "n8n-vpc")
        self.assertEqual(config.subnet_name, "n8n-subnet")
        self.assertEqual(config.database_type, "sqlite")
        self.assertEqual(config.cloudsql_instance_name, "")
        self.assertEqual(config.cloudsql_tier, "db-f1-micro")
        self.assertEqual(config.n8n_namespace, "n8n")
        self.assertEqual(config.n8n_host, "")
        self.assertEqual(config.n8n_protocol, "http")
        self.assertEqual(config.n8n_encryption_key, "")
        self.assertFalse(config.enable_tls)
        self.assertEqual(config.tls_provider, "letsencrypt")
        self.assertEqual(config.letsencrypt_email, "")
        self.assertFalse(config.enable_basic_auth)
        self.assertEqual(config.basic_auth_username, "admin")
        self.assertEqual(config.basic_auth_password, "")

    def test_to_dict(self):
        """Test GCPDeploymentConfig.to_dict() serialization"""
        config = GCPDeploymentConfig()
        config.gcp_project_id = "test-project-123"
        config.gcp_region = "us-west1"
        config.gcp_zone = "us-west1-b"
        config.cluster_name = "test-cluster"
        config.n8n_encryption_key = "abc123def456"

        result = config.to_dict()

        self.assertIsInstance(result, dict)
        self.assertEqual(result['cloud_provider'], "gcp")
        self.assertEqual(result['gcp_project_id'], "test-project-123")
        self.assertEqual(result['gcp_region'], "us-west1")
        self.assertEqual(result['gcp_zone'], "us-west1-b")
        self.assertEqual(result['cluster_name'], "test-cluster")
        self.assertEqual(result['n8n_encryption_key'], "abc123def456")

        # Ensure all 22 attributes are in the dict (cloud_provider + 21 config fields)
        self.assertEqual(len(result), 22)

    def test_cloudsql_configuration(self):
        """Test GCPDeploymentConfig with Cloud SQL settings"""
        config = GCPDeploymentConfig()
        config.database_type = "cloudsql"
        config.cloudsql_instance_name = "n8n-postgres-prod"
        config.cloudsql_tier = "db-n1-standard-1"

        result = config.to_dict()
        self.assertEqual(result['database_type'], "cloudsql")
        self.assertEqual(result['cloudsql_instance_name'], "n8n-postgres-prod")
        self.assertEqual(result['cloudsql_tier'], "db-n1-standard-1")

    def test_tls_configuration(self):
        """Test GCPDeploymentConfig with TLS enabled"""
        config = GCPDeploymentConfig()
        config.enable_tls = True
        config.n8n_protocol = "https"
        config.letsencrypt_email = "admin@example.com"

        result = config.to_dict()
        self.assertTrue(result['enable_tls'])
        self.assertEqual(result['n8n_protocol'], "https")
        self.assertEqual(result['letsencrypt_email'], "admin@example.com")


class TestGCPAuthChecker(unittest.TestCase):
    """Test GCPAuthChecker class"""

    @patch('subprocess.run')
    def test_list_projects_success(self, mock_run):
        """Test list_projects returns project list successfully"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps([
                {"projectId": "project-1", "name": "Test Project 1"},
                {"projectId": "project-2", "name": "Test Project 2"}
            ])
        )

        projects = GCPAuthChecker.list_projects()

        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0]['projectId'], "project-1")
        self.assertEqual(projects[1]['name'], "Test Project 2")
        mock_run.assert_called_once_with(
            ['gcloud', 'projects', 'list', '--format=json'],
            capture_output=True,
            text=True,
            timeout=30
        )

    @patch('subprocess.run')
    def test_list_projects_no_name(self, mock_run):
        """Test list_projects handles projects without name field"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps([
                {"projectId": "project-3"}
            ])
        )

        projects = GCPAuthChecker.list_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]['name'], "project-3")  # Falls back to projectId

    @patch('subprocess.run')
    def test_list_projects_error(self, mock_run):
        """Test list_projects returns empty list on error"""
        mock_run.return_value = Mock(returncode=1, stdout="")

        projects = GCPAuthChecker.list_projects()

        self.assertEqual(projects, [])

    @patch('subprocess.run')
    def test_list_projects_timeout(self, mock_run):
        """Test list_projects handles timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired('gcloud', 30)

        projects = GCPAuthChecker.list_projects()

        self.assertEqual(projects, [])

    @patch('subprocess.run')
    def test_verify_credentials_success(self, mock_run):
        """Test verify_credentials succeeds with valid credentials"""
        # Mock gcloud auth list and project describe
        mock_run.side_effect = [
            Mock(
                returncode=0,
                stdout=json.dumps([{
                    "account": "user@example.com",
                    "status": "ACTIVE"
                }])
            ),
            Mock(
                returncode=0,
                stdout=json.dumps({
                    "projectId": "test-project",
                    "name": "Test Project"
                })
            )
        ]

        success, message = GCPAuthChecker.verify_credentials("test-project")

        self.assertTrue(success)
        self.assertIn("user@example.com", message)
        self.assertIn("Test Project", message)

    @patch('subprocess.run')
    def test_verify_credentials_no_active_account(self, mock_run):
        """Test verify_credentials fails when no active account"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps([])  # Empty list, no active accounts
        )

        success, message = GCPAuthChecker.verify_credentials("test-project")

        self.assertFalse(success)
        self.assertIn("No active gcloud", message)

    @patch('subprocess.run')
    def test_verify_credentials_project_not_found(self, mock_run):
        """Test verify_credentials fails when project not accessible"""
        mock_run.side_effect = [
            Mock(
                returncode=0,
                stdout=json.dumps([{
                    "account": "user@example.com",
                    "status": "ACTIVE"
                }])
            ),
            Mock(returncode=1, stderr="Project not found")
        ]

        success, message = GCPAuthChecker.verify_credentials("test-project")

        self.assertFalse(success)
        self.assertIn("Cannot access project", message)

    @patch('subprocess.run')
    def test_check_required_apis_all_enabled(self, mock_run):
        """Test check_required_apis when all APIs are enabled"""
        enabled_apis = [
            {"config": {"name": "compute.googleapis.com"}},
            {"config": {"name": "container.googleapis.com"}},
            {"config": {"name": "cloudresourcemanager.googleapis.com"}},
            {"config": {"name": "iam.googleapis.com"}},
            {"config": {"name": "iamcredentials.googleapis.com"}},
            {"config": {"name": "secretmanager.googleapis.com"}},
            {"config": {"name": "sqladmin.googleapis.com"}},
            {"config": {"name": "servicenetworking.googleapis.com"}},
            {"config": {"name": "logging.googleapis.com"}},
            {"config": {"name": "monitoring.googleapis.com"}}
        ]

        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(enabled_apis)
        )

        apis_ok, missing = GCPAuthChecker.check_required_apis("test-project")

        self.assertTrue(apis_ok)
        self.assertEqual(missing, [])

    @patch('subprocess.run')
    def test_check_required_apis_some_missing(self, mock_run):
        """Test check_required_apis when some APIs are missing"""
        enabled_apis = [
            {"config": {"name": "compute.googleapis.com"}},
            {"config": {"name": "container.googleapis.com"}}
        ]

        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(enabled_apis)
        )

        apis_ok, missing = GCPAuthChecker.check_required_apis("test-project")

        self.assertFalse(apis_ok)
        self.assertGreater(len(missing), 0)
        self.assertIn("iam.googleapis.com", missing)
        self.assertIn("secretmanager.googleapis.com", missing)


class TestDependencyCheckerGCP(unittest.TestCase):
    """Test DependencyChecker with GCP support"""

    @patch('subprocess.run')
    @patch('shutil.which')
    @patch('builtins.print')
    def test_check_all_dependencies_gcp(self, mock_print, mock_which, mock_run):
        """Test check_all_dependencies with cloud_provider='gcp'"""
        # Mock all tools as installed
        mock_which.return_value = '/usr/bin/tool'

        # Mock version checks
        def mock_subprocess(*args, **kwargs):
            cmd = args[0]
            if 'terraform' in cmd:
                return Mock(returncode=0, stdout="Terraform v1.6.0")
            elif 'helm' in cmd:
                return Mock(returncode=0, stdout="v3.10.0")
            elif 'kubectl' in cmd:
                return Mock(returncode=0, stdout="Client Version: v1.25.0")
            elif 'openssl' in cmd:
                return Mock(returncode=0, stdout="OpenSSL 1.1.1")
            elif 'gcloud' in cmd:
                return Mock(returncode=0, stdout="Google Cloud SDK 450.0.0")
            return Mock(returncode=1)

        mock_run.side_effect = mock_subprocess

        success, missing = DependencyChecker.check_all_dependencies(cloud_provider="gcp")

        self.assertTrue(success)
        self.assertEqual(missing, [])

    @patch('subprocess.run')
    @patch('shutil.which')
    @patch('builtins.print')
    def test_check_all_dependencies_gcp_missing_gcloud(self, mock_print, mock_which, mock_run):
        """Test check_all_dependencies detects missing gcloud"""
        # Mock all tools except gcloud
        def mock_which_func(tool):
            return '/usr/bin/tool' if tool != 'gcloud' else None

        mock_which.side_effect = mock_which_func

        def mock_subprocess(*args, **kwargs):
            cmd = args[0]
            if 'terraform' in cmd:
                return Mock(returncode=0, stdout="Terraform v1.6.0")
            elif 'helm' in cmd:
                return Mock(returncode=0, stdout="v3.10.0")
            elif 'kubectl' in cmd:
                return Mock(returncode=0, stdout="Client Version: v1.25.0")
            elif 'openssl' in cmd:
                return Mock(returncode=0, stdout="OpenSSL 1.1.1")
            return Mock(returncode=1)

        mock_run.side_effect = mock_subprocess

        success, missing = DependencyChecker.check_all_dependencies(cloud_provider="gcp")

        self.assertFalse(success)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0][0], 'gcloud')

    def test_gcp_tools_definition(self):
        """Test GCP_TOOLS dictionary is properly defined"""
        self.assertIn('gcloud', DependencyChecker.GCP_TOOLS)
        gcloud_tool = DependencyChecker.GCP_TOOLS['gcloud']

        self.assertIn('command', gcloud_tool)
        self.assertIn('version_regex', gcloud_tool)
        self.assertIn('min_version', gcloud_tool)
        self.assertIn('install_url', gcloud_tool)
        self.assertIn('description', gcloud_tool)

        self.assertEqual(gcloud_tool['min_version'], '400.0.0')


class TestConfigHistoryManagerGCP(unittest.TestCase):
    """Test ConfigHistoryManager with GCP configurations"""

    def setUp(self):
        """Create temporary directory for test files"""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up temporary directory"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_save_gcp_configuration(self):
        """Test saving GCP configuration to history"""
        config = GCPDeploymentConfig()
        config.gcp_project_id = "test-project-456"
        config.gcp_region = "us-east1"
        config.cluster_name = "test-gke"
        config.n8n_encryption_key = "secret123"

        ConfigHistoryManager.save_configuration(config, "gcp", self.temp_dir)

        # Check history file was created
        history_file = self.temp_dir / "setup_history.log"
        self.assertTrue(history_file.exists())

        content = history_file.read_text()
        self.assertIn("GCP", content)
        self.assertIn("test-project-456", content)
        self.assertIn("us-east1", content)
        self.assertIn("test-gke", content)
        # Encryption key should be redacted
        self.assertIn("***REDACTED***", content)
        self.assertNotIn("secret123", content)

    def test_save_gcp_configuration_json(self):
        """Test saving GCP configuration to JSON file"""
        config = GCPDeploymentConfig()
        config.gcp_project_id = "json-test-project"
        config.database_type = "cloudsql"
        config.cloudsql_instance_name = "test-db"

        ConfigHistoryManager.save_configuration(config, "gcp", self.temp_dir)

        # Check JSON file was created
        json_file = self.temp_dir / ".setup-current.json"
        self.assertTrue(json_file.exists())

        with open(json_file, 'r') as f:
            data = json.load(f)

        self.assertEqual(data['cloud_provider'], "gcp")
        self.assertEqual(data['configuration']['gcp_project_id'], "json-test-project")
        self.assertEqual(data['configuration']['database_type'], "cloudsql")
        self.assertEqual(data['configuration']['cloudsql_instance_name'], "test-db")

    def test_load_gcp_configuration(self):
        """Test loading GCP configuration from JSON"""
        # Create a JSON config file
        config_data = {
            'timestamp': '2025-01-01 12:00:00',
            'cloud_provider': 'gcp',
            'configuration': {
                'gcp_project_id': 'loaded-project',
                'gcp_region': 'europe-west1',
                'cluster_name': 'loaded-cluster'
            }
        }

        json_file = self.temp_dir / ".setup-current.json"
        with open(json_file, 'w') as f:
            json.dump(config_data, f)

        # Load configuration
        loaded = ConfigHistoryManager.load_previous_configuration(self.temp_dir)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded['cloud_provider'], 'gcp')
        self.assertEqual(loaded['configuration']['gcp_project_id'], 'loaded-project')

    def test_format_history_entry_gcp(self):
        """Test _format_history_entry includes GCP fields"""
        config_dict = {
            'cloud_provider': 'gcp',
            'gcp_project_id': 'test-project',
            'gcp_region': 'us-central1',
            'gcp_zone': 'us-central1-a',
            'vpc_name': 'test-vpc',
            'subnet_name': 'test-subnet',
            'cluster_name': 'test-cluster',
            'node_machine_type': 'e2-medium',
            'database_type': 'cloudsql',
            'cloudsql_instance_name': 'test-db',
            'cloudsql_tier': 'db-f1-micro',
            'enable_tls': True,
            'tls_provider': 'letsencrypt'
        }

        entry = ConfigHistoryManager._format_history_entry(
            "2025-01-01 10:00:00",
            "gcp",
            config_dict
        )

        # Check all GCP fields are included
        self.assertIn("gcp_project_id", entry)
        self.assertIn("test-project", entry)
        self.assertIn("gcp_region", entry)
        self.assertIn("us-central1", entry)
        self.assertIn("gcp_zone", entry)
        self.assertIn("us-central1-a", entry)
        self.assertIn("vpc_name", entry)
        self.assertIn("test-vpc", entry)
        self.assertIn("node_machine_type", entry)
        self.assertIn("e2-medium", entry)
        self.assertIn("cloudsql_instance_name", entry)
        self.assertIn("test-db", entry)
        self.assertIn("enable_tls", entry)
        self.assertIn("True", entry)


class TestConfigurationPromptGCP(unittest.TestCase):
    """Test ConfigurationPrompt with GCP"""

    def test_init_gcp_provider(self):
        """Test ConfigurationPrompt.__init__ with cloud_provider='gcp'"""
        prompt = ConfigurationPrompt(cloud_provider="gcp")

        self.assertEqual(prompt.cloud_provider, "gcp")
        self.assertIsInstance(prompt.config, GCPDeploymentConfig)

    @patch('builtins.input')
    @patch('setup.GCPAuthChecker.list_projects')
    @patch('setup.GCPAuthChecker.verify_credentials')
    @patch('setup.GCPAuthChecker.check_required_apis')
    @patch('builtins.print')
    def test_collect_gcp_configuration_single_project(
        self, mock_print, mock_check_apis, mock_verify, mock_list_projects, mock_input
    ):
        """Test collect_gcp_configuration with single project"""
        # Mock single project
        mock_list_projects.return_value = [
            {"projectId": "solo-project", "name": "Solo Project"}
        ]
        mock_verify.return_value = (True, "Authenticated")
        mock_check_apis.return_value = (True, [])

        # Mock user inputs
        mock_input.side_effect = [
            "",  # region (default us-central1)
            "",  # cluster name (default)
            "3",  # machine type choice (3 = e2-medium, which is option index 2)
            "",  # node count (default 1)
            "",  # vpc name
            "",  # subnet name
            "",  # namespace
            "n8n-gcp.example.com",  # hostname
            "",  # timezone
            "y",  # generate encryption key
            "1",  # database type (SQLite)
            "y"   # proceed
        ]

        prompt = ConfigurationPrompt(cloud_provider="gcp")
        config = prompt.collect_gcp_configuration(skip_tls=True)

        self.assertEqual(config.gcp_project_id, "solo-project")
        self.assertEqual(config.gcp_region, "us-central1")
        self.assertEqual(config.cluster_name, "n8n-gke-cluster")
        # The actual machine type depends on the choice menu, so we'll just check it's set
        self.assertIn(config.node_machine_type, ["e2-micro", "e2-small", "e2-medium", "n1-standard-1", "n1-standard-2"])
        self.assertEqual(config.database_type, "sqlite")
        self.assertEqual(config.n8n_host, "n8n-gcp.example.com")

    @patch('builtins.input')
    @patch('setup.GCPAuthChecker.list_projects')
    @patch('builtins.print')
    def test_collect_gcp_configuration_no_projects(
        self, mock_print, mock_list_projects, mock_input
    ):
        """Test collect_gcp_configuration fails when no projects found"""
        mock_list_projects.return_value = []

        prompt = ConfigurationPrompt(cloud_provider="gcp")

        with self.assertRaises(SetupInterrupted):
            prompt.collect_gcp_configuration(skip_tls=True)

    @patch('builtins.input')
    @patch('setup.GCPAuthChecker.list_projects')
    @patch('setup.GCPAuthChecker.verify_credentials')
    @patch('builtins.print')
    def test_collect_gcp_configuration_auth_failure(
        self, mock_print, mock_verify, mock_list_projects, mock_input
    ):
        """Test collect_gcp_configuration fails on auth failure"""
        mock_list_projects.return_value = [
            {"projectId": "test-project", "name": "Test"}
        ]
        mock_verify.return_value = (False, "Authentication failed")

        prompt = ConfigurationPrompt(cloud_provider="gcp")

        with self.assertRaises(SetupInterrupted):
            prompt.collect_gcp_configuration(skip_tls=True)


if __name__ == '__main__':
    unittest.main()
