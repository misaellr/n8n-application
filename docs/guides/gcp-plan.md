# plan

## purpose

this plan defines the implementation roadmap for adding Google Cloud Platform (GCP) as a third cloud provider option to the n8n deployment automation (setup.py), alongside existing AWS and Azure support. the implementation will enable automated deployment of n8n on Google Kubernetes Engine (GKE) following proven patterns from successful AWS EKS and Azure AKS implementations. upon completion, users will be able to deploy n8n on GKE using `python3 setup.py --cloud-provider gcp` with the same automated experience as AWS and Azure.

## assumptions

- the implementation team has access to a GCP project with owner or equivalent permissions for testing
- existing AWS and Azure implementations in setup.py are stable and serve as authoritative reference patterns
- GCP APIs (compute, container, secretmanager, sqladmin) can be enabled programmatically or are pre-enabled
- the terraform google provider (hashicorp/google) version 5.0+ will be used
- GKE workload identity is the preferred authentication method for pod-to-GCP service communication
- Cloud SQL proxy sidecar pattern is acceptable for PostgreSQL connectivity
- the implementation will target Python 3.8+ compatibility (matching existing codebase)
- gcloud CLI SDK is installed and configured on deployment machines
- cost estimates are based on us-central1 region pricing as of October 2025
- Let's Encrypt HTTP-01 challenge method will be used (no DNS-01 challenge support required)
- the existing Helm chart (charts/n8n) is cloud-agnostic and requires minimal GCP-specific changes

## success metrics

- 100% of AWS/Azure deployment features replicated for GCP (4-phase deployment, TLS, basic auth, teardown)
- deployment time for GKE cluster (SQLite configuration): under 30 minutes end-to-end
- all automated tests pass: unit tests (configuration, auth), integration tests (deploy, teardown)
- successful deployment verified in 3 GCP regions: us-central1, us-east1, europe-west1
- zero critical or high-severity security findings in IAM permissions and service account configurations
- documentation completeness: 100% of setup.py features documented in gcp-requirements.md
- user acceptance: successful deployment by 2 external testers following documentation only

## non-goals

- GKE autopilot support (standard GKE clusters only)
- multi-cluster or multi-region active-active deployments
- GCP marketplace listing or one-click deployment
- custom VPC peering configurations beyond Cloud SQL requirements
- support for GCP Anthos or hybrid cloud scenarios
- migration tooling from AWS/Azure to GCP
- GCP-specific monitoring dashboards (Cloud Operations integration is manual)
- automated DNS configuration with Cloud DNS (manual CNAME/A record setup required)
- IPv6 networking support
- Windows container node pools

---

## phase 1 – foundation and configuration

### outcome (what success looks like)

this phase establishes the foundational Python code for GCP support within setup.py, including the configuration data model, authentication verification, and interactive user prompts. by the end of this phase, the system can collect and validate all required GCP-specific configuration parameters (project ID, region, cluster settings, database type) from users through an interactive CLI, verify GCP credentials and API enablement, and prepare structured configuration data ready for terraform and helm deployment in subsequent phases. all code follows existing AWS/Azure patterns for consistency.

### scope (in)

- GCPDeploymentConfig class with all required attributes
- GCPAuthChecker class for credential and API verification
- interactive configuration prompts in ConfigurationPrompt class (collect_gcp_configuration method)
- dependency checker updates to include gcloud CLI verification
- configuration validation logic (project ID format, region validity, machine type validation)
- integration with existing ConfigHistoryManager for configuration logging

### negative scope (out)

- terraform module creation (deferred to phase 2)
- helm deployment logic (deferred to phase 3)
- actual GCP resource creation
- teardown functionality (deferred to phase 4)
- TLS or basic authentication configuration logic

### deliverables

- GCPDeploymentConfig class in setup.py (~100 lines)
- GCPAuthChecker class in setup.py (~150 lines)
- collect_gcp_configuration method in ConfigurationPrompt class (~200 lines)
- updated DependencyChecker.GCP_TOOLS dictionary
- updated DependencyChecker.check_all_dependencies method
- unit tests for configuration validation
- updated setup_history.log format to support GCP entries

### acceptance criteria (phase-level)

1. GCPDeploymentConfig class instantiates successfully with all 18 required attributes
2. GCPAuthChecker.verify_credentials returns (True, "authenticated as ...") for valid gcloud credentials
3. GCPAuthChecker.check_required_apis identifies missing APIs correctly across 10 required GCP APIs
4. collect_gcp_configuration method completes interactive flow and returns valid GCPDeploymentConfig object
5. configuration history is saved to setup_history.log in correct markdown format with "GCP" cloud provider tag
6. dependency checker reports missing gcloud CLI when not installed

### uat (user acceptance tests)

- **scenario: complete GCP configuration collection with valid inputs**
  - steps: run setup.py → select GCP provider → provide valid project ID → select us-central1 region → accept default cluster name → choose SQLite database → provide domain name → skip TLS
  - expected result: GCPDeploymentConfig object created with all attributes populated, configuration saved to setup_history.log
  - evidence: [placeholder for screenshot of successful configuration completion]

- **scenario: detect invalid GCP credentials**
  - steps: logout from gcloud (`gcloud auth revoke`) → run setup.py → select GCP provider → attempt configuration
  - expected result: GCPAuthChecker.verify_credentials returns (False, "not authenticated") and user is prompted to run `gcloud auth login`
  - evidence: [placeholder for error message screenshot]

- **scenario: detect missing GCP APIs**
  - steps: disable container.googleapis.com API in test project → run setup.py → select GCP → provide project ID
  - expected result: GCPAuthChecker.check_required_apis returns list containing container.googleapis.com and displays message to enable it
  - evidence: [placeholder for API check output]

### tasks

- **task 1.1: create GCPDeploymentConfig class**
  - description: implement the GCPDeploymentConfig data class in setup.py following the pattern of AWSDeploymentConfig and AzureDeploymentConfig. include 18 attributes covering GCP-specific settings (project ID, region, zone), cluster configuration (name, machine type, node count), network settings (VPC, subnet), database settings (SQLite or Cloud SQL), application settings (namespace, hostname, encryption key), TLS settings (enable, provider, email), and basic auth settings (enable, username, password). include to_dict() method for serialization to configuration history.
  - acceptance criteria:
    1. class contains exactly 18 attributes with correct type annotations (str, int, bool)
    2. to_dict() method returns dictionary with all attributes serializable to JSON
    3. default values are set for optional attributes (e.g., node_count=1, database_type="sqlite")
    4. class docstring documents purpose and mapping to AWS/Azure equivalents
  - test scenario(s):
    - **scenario: instantiate config with minimal parameters**
      - steps: create GCPDeploymentConfig(gcp_project_id="test-project", gcp_region="us-central1") → call to_dict()
      - expected result: object created, to_dict() returns dict with 18 keys, defaults applied
      - evidence: [placeholder for unit test output]
    - **scenario: config serialization to JSON**
      - steps: create config → json.dumps(config.to_dict())
      - expected result: JSON string generated without errors
      - evidence: [placeholder for JSON output sample]
  - owner: backend engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase1:1.1): create GCPDeploymentConfig class with 18 attributes
    - record commit sha in evidence link

- **task 1.2: implement GCPAuthChecker class**
  - description: create GCPAuthChecker class with three static methods: list_projects() to enumerate accessible GCP projects using `gcloud projects list --format=json`, verify_credentials(project_id) to validate authentication and project access using `gcloud auth list` and `gcloud projects describe`, and check_required_apis(project_id) to verify that 10 required GCP APIs (compute, container, cloudresourcemanager, iam, iamcredentials, secretmanager, sqladmin, dns, servicenetworking, logging, monitoring) are enabled using `gcloud services list --enabled`. implement subprocess-based command execution with 30-second timeouts matching AWS auth checker pattern.
  - acceptance criteria:
    1. list_projects() returns list of project IDs when user is authenticated
    2. verify_credentials() returns (True, "authenticated as user@example.com") for valid auth
    3. verify_credentials() returns (False, "not authenticated") when gcloud auth is revoked
    4. check_required_apis() correctly identifies enabled vs disabled APIs
    5. all methods handle subprocess timeout exceptions gracefully
    6. command output parsing handles JSON format correctly with error checking
  - test scenario(s):
    - **scenario: verify valid authentication**
      - steps: authenticate with `gcloud auth login` → call verify_credentials("valid-project-id")
      - expected result: returns (True, message) with authenticated user email
      - evidence: [placeholder for test output]
    - **scenario: detect unauthenticated state**
      - steps: revoke auth with `gcloud auth revoke` → call verify_credentials("any-project")
      - expected result: returns (False, "not authenticated") or (False, "gcloud auth required")
      - evidence: [placeholder for error message]
    - **scenario: check API enablement**
      - steps: call check_required_apis(test_project_id) with known API states
      - expected result: returns (True, []) if all enabled, or (False, ["missing-api"]) if any disabled
      - evidence: [placeholder for API check results]
  - owner: backend engineer
  - estimate: 5 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase1:1.2): implement GCPAuthChecker with credential and API verification
    - record commit sha in evidence link

- **task 1.3: implement collect_gcp_configuration method**
  - description: add collect_gcp_configuration(skip_tls=False) method to ConfigurationPrompt class, implementing interactive CLI prompts for all GCP-specific configuration. prompt sequence: (1) list and select GCP project using GCPAuthChecker.list_projects(), (2) verify credentials for selected project, (3) check and optionally enable required APIs, (4) select region from list (us-central1, us-east1, us-west1, europe-west1, asia-southeast1) with us-central1 default, (5) select zone based on region (auto-append -a), (6) cluster configuration (name default: n8n-gke-cluster, machine type default: e2-medium, node count default: 1), (7) database type (SQLite default or Cloud SQL), (8) domain name, (9) TLS configuration (if not skip_tls), (10) basic auth configuration (if not skip_tls). return fully populated GCPDeploymentConfig object.
  - acceptance criteria:
    1. method prompts for all 10 configuration sections in correct order
    2. defaults are applied when user presses Enter without input
    3. input validation rejects invalid formats (e.g., invalid project ID format, invalid region)
    4. Cloud SQL sub-prompts (instance name, tier) appear only when Cloud SQL is selected
    5. method returns GCPDeploymentConfig object with all required attributes populated
    6. user can cancel at any prompt and exit gracefully
  - test scenario(s):
    - **scenario: complete configuration with all defaults**
      - steps: run method → accept all defaults by pressing Enter repeatedly
      - expected result: GCPDeploymentConfig object returned with default values (SQLite, e2-medium, node_count=1, etc.)
      - evidence: [placeholder for config output]
    - **scenario: configure Cloud SQL database**
      - steps: run method → select Cloud SQL → provide instance name → select db-f1-micro tier
      - expected result: config.database_type="cloudsql", config.cloudsql_instance_name populated, config.cloudsql_tier="db-f1-micro"
      - evidence: [placeholder for Cloud SQL config]
    - **scenario: validate project ID format**
      - steps: run method → enter invalid project ID (contains uppercase or special chars) → observe validation error
      - expected result: error message displayed, re-prompt for valid project ID
      - evidence: [placeholder for validation error]
  - owner: backend engineer
  - estimate: 6 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase1:1.3): implement GCP configuration prompts with validation
    - record commit sha in evidence link

- **task 1.4: update DependencyChecker for GCP**
  - description: modify DependencyChecker class to add GCP_TOOLS dictionary containing gcloud CLI check configuration, and update check_all_dependencies(cloud_provider) method to include GCP case that merges COMMON_TOOLS and GCP_TOOLS. verify gcloud CLI installation and version (require 400.0.0+). update dependency check output messages to include GCP-specific instructions ("install gcloud: https://cloud.google.com/sdk/docs/install").
  - acceptance criteria:
    1. GCP_TOOLS dictionary added with gcloud check command ['gcloud', 'version']
    2. check_all_dependencies("gcp") includes gcloud in required tools
    3. dependency check passes when gcloud 400.0.0+ is installed
    4. dependency check fails with helpful error message when gcloud is missing
    5. error message includes installation URL for gcloud SDK
  - test scenario(s):
    - **scenario: verify gcloud dependency check**
      - steps: call check_all_dependencies("gcp") with gcloud installed
      - expected result: returns (True, []) indicating all dependencies present
      - evidence: [placeholder for check output]
    - **scenario: detect missing gcloud CLI**
      - steps: temporarily rename gcloud binary → call check_all_dependencies("gcp")
      - expected result: returns (False, ['gcloud']) with installation instructions
      - evidence: [placeholder for missing dependency message]
  - owner: backend engineer
  - estimate: 2 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase1:1.4): add gcloud CLI to dependency checker
    - record commit sha in evidence link

- **task 1.5: integrate GCP config with history manager**
  - description: verify ConfigHistoryManager correctly handles GCP configurations by testing save_configuration() with GCPDeploymentConfig object and "gcp" cloud provider string. ensure setup_history.log format includes GCP-specific attributes in readable markdown format. verify current config is saved to .setup-current.json with cloud_provider="gcp".
  - acceptance criteria:
    1. save_configuration(gcp_config, "gcp", base_dir) executes without errors
    2. setup_history.log contains entry with "Cloud Provider: GCP" header
    3. GCP-specific fields (gcp_project_id, gcp_region, gcp_zone) appear in history log
    4. .setup-current.json contains valid JSON with cloud_provider="gcp"
    5. timestamp format matches existing AWS/Azure entries
  - test scenario(s):
    - **scenario: save GCP configuration to history**
      - steps: create GCPDeploymentConfig → call save_configuration() → inspect setup_history.log
      - expected result: log file contains GCP entry with timestamp, project ID, region visible
      - evidence: [placeholder for log file excerpt]
    - **scenario: verify JSON current config**
      - steps: save config → read .setup-current.json → parse JSON
      - expected result: JSON contains cloud_provider="gcp" and all config attributes
      - evidence: [placeholder for JSON structure]
  - owner: backend engineer
  - estimate: 2 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase1:1.5): integrate GCP config with history manager
    - record commit sha in evidence link

- **task 1.6: create unit tests for phase 1**
  - description: write comprehensive unit tests covering GCPDeploymentConfig instantiation, to_dict() serialization, GCPAuthChecker mock scenarios (authenticated, not authenticated, timeout), collect_gcp_configuration validation logic (without actual user interaction using mock inputs), and dependency checker GCP case. use pytest framework matching existing test patterns. achieve 90%+ code coverage for new GCP code.
  - acceptance criteria:
    1. minimum 15 unit test cases covering all phase 1 code
    2. all tests pass with pytest
    3. code coverage for GCPDeploymentConfig: 100%
    4. code coverage for GCPAuthChecker: 90%+
    5. code coverage for collect_gcp_configuration: 85%+
    6. tests use mocking for subprocess calls (no actual gcloud execution)
  - test scenario(s):
    - **scenario: run all unit tests**
      - steps: execute pytest with coverage → review coverage report
      - expected result: all tests pass, coverage targets met
      - evidence: [placeholder for pytest output and coverage report]
  - owner: backend engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: test(phase1:1.6): add unit tests for GCP configuration classes
    - record commit sha in evidence link

### risks and mitigations

- **risk: gcloud CLI version incompatibility across different OS** → **mitigation:** test on macOS, Ubuntu, and WSL2; document minimum version 400.0.0; implement version parsing to warn users
- **risk: GCP project ID format variations (legacy vs new format)** → **mitigation:** implement regex validation accepting both formats; reference official GCP project ID rules
- **risk: API enablement requires elevated permissions** → **mitigation:** provide clear error messages directing users to enable APIs manually via console; document required permissions in gcp-requirements.md
- **risk: interactive prompts difficult to test** → **mitigation:** use dependency injection for input/output streams; create mock input sequences for automated testing
- **risk: configuration validation insufficient** → **mitigation:** implement comprehensive validation for all user inputs; provide helpful error messages with examples

### dependencies

- existing setup.py codebase (AWS and Azure implementations stable)
- gcloud CLI installed on development machines for testing
- access to GCP test project with owner permissions
- Python 3.8+ environment
- pytest testing framework

### completion checklist (exit criteria)

- [ ] all phase-level acceptance criteria met
- [ ] all task test scenarios passed
- [ ] uat executed and recorded
- [ ] documentation updated (links)
- [ ] phase commit created and pushed (sha recorded)
- [ ] code review completed and approved
- [ ] unit test coverage targets met (90%+)
- [ ] no critical or high severity lint or security issues

### git actions (end of phase)

- create a commit summarizing the phase completion
- push to the remote repository
- record branch and commit sha

### phase execution report

*(fill after execution)*

- **what was done:**
  - tasks completed with links and evidence

- **test results summary:**
  - scenarios run: 0
  - pass: 0
  - fail: 0
  - defects found: 0 (links)

- **challenges encountered:**
  - description and how each was handled

- **learnings:**
  - key takeaways and recommendations

- **decision:**
  - go/no-go and rationale

- **git evidence:**
  - task commits: list shas
  - phase commit and push: branch and sha

- **next phase readiness:**
  - entry criteria confirmed

---

## phase 2 – terraform infrastructure modules

### outcome (what success looks like)

this phase delivers production-ready terraform modules that provision complete GKE infrastructure on GCP, including VPC networking, GKE cluster with node pools, service accounts with proper IAM bindings, Secret Manager integration, and optional Cloud SQL PostgreSQL. by the end of this phase, running `terraform apply` in the terraform/gcp directory successfully creates a fully functional GKE cluster with all supporting resources, outputs kubectl configuration commands, and stores encryption keys in Secret Manager. the infrastructure matches AWS VPC and Azure VNet patterns for consistency and follows GCP best practices for security and networking.

### scope (in)

- terraform/gcp directory structure and all .tf files
- VPC network with public and private subnets (VPC-native cluster)
- Cloud NAT for outbound internet access from private nodes
- GKE regional cluster with workload identity enabled
- node pool configuration with configurable machine type and count
- three service accounts (cluster, nodes, workload) with minimal IAM roles
- Secret Manager secrets for n8n encryption key and basic auth
- optional Cloud SQL PostgreSQL instance with private IP
- firewall rules for GKE ingress and internal communication
- terraform outputs for kubectl config, secrets, and database details
- variables.tf with validation rules
- terraform backend configuration for GCS state storage

### negative scope (out)

- GKE autopilot (standard clusters only)
- multi-cluster or multi-region setups
- custom VPC peering beyond Cloud SQL requirements
- Cloud Armor or advanced security features
- terraform module for nginx-ingress (handled by Helm in phase 3)
- terraform module for cert-manager (handled by Helm in phase 3)
- Cloud DNS zone creation (manual DNS configuration)

### deliverables

- terraform/gcp/main.tf (infrastructure orchestration)
- terraform/gcp/variables.tf (input variables with validation)
- terraform/gcp/outputs.tf (resource outputs for kubectl and helm)
- terraform/gcp/versions.tf (provider version constraints)
- terraform/gcp/vpc.tf (networking resources)
- terraform/gcp/gke.tf (cluster and node pool)
- terraform/gcp/secrets.tf (Secret Manager resources)
- terraform/gcp/cloudsql.tf (optional PostgreSQL)
- terraform/gcp/iam.tf (service accounts and role bindings)
- terraform/gcp/terraform.tfvars.example (sample configuration)
- terraform/gcp/.terraform-version (version pinning)
- README.md in terraform/gcp (usage instructions)

### acceptance criteria (phase-level)

1. terraform init completes successfully with google provider 5.0+
2. terraform validate passes with no errors
3. terraform plan shows creation of 25-35 resources (varies with Cloud SQL option)
4. terraform apply creates GKE cluster accessible via kubectl in under 25 minutes
5. all three service accounts created with correct IAM role bindings
6. workload identity binding works (pod can access Secret Manager)
7. Cloud NAT provides outbound internet to private nodes (verified via pod egress test)
8. Cloud SQL instance (if enabled) accepts connections from GKE pods via private IP
9. encryption key stored in Secret Manager is retrievable
10. terraform destroy removes all resources cleanly without orphans

### uat (user acceptance tests)

- **scenario: deploy GKE cluster with SQLite (no Cloud SQL)**
  - steps: create terraform.tfvars with database_type="sqlite" → terraform init → terraform plan → terraform apply → verify cluster creation via `gcloud container clusters list`
  - expected result: cluster status "RUNNING", node pool status "RUNNING", kubectl context configured, no Cloud SQL resources created
  - evidence: [placeholder for gcloud cluster list output]

- **scenario: deploy GKE cluster with Cloud SQL PostgreSQL**
  - steps: create terraform.tfvars with database_type="cloudsql" → terraform apply → verify Cloud SQL instance via `gcloud sql instances list` → test pod connectivity to Cloud SQL
  - expected result: Cloud SQL instance status "RUNNABLE", private IP assigned, connectivity test from pod succeeds
  - evidence: [placeholder for Cloud SQL connectivity test]

- **scenario: verify workload identity binding**
  - steps: deploy test pod with workload identity annotation → pod attempts to read Secret Manager secret → check pod logs
  - expected result: pod successfully retrieves secret value without error
  - evidence: [placeholder for pod log showing secret access]

- **scenario: verify Cloud NAT outbound access**
  - steps: deploy test pod in private subnet → pod executes `curl https://www.google.com` → check response
  - expected result: HTTP 200 response from external URL, proving egress via Cloud NAT
  - evidence: [placeholder for curl output from pod]

- **scenario: teardown infrastructure cleanly**
  - steps: terraform destroy → verify all resources removed via `gcloud compute networks list` and `gcloud container clusters list`
  - expected result: no resources remain, GCS state file shows empty state
  - evidence: [placeholder for terraform destroy output]

### tasks

- **task 2.1: create terraform directory structure and base files**
  - description: create terraform/gcp directory with initial structure. create versions.tf pinning google provider to ~> 5.0, google-beta provider for preview features. create main.tf with provider configuration (project, region, credentials). create variables.tf with variable definitions for all configuration parameters (project_id, region, zone, cluster_name, node_machine_type, node_count, database_type, cloudsql_tier, etc.) including validation rules. create outputs.tf stub. create .terraform-version file pinning terraform to 1.6+. create .gitignore for terraform state files.
  - acceptance criteria:
    1. terraform/gcp directory created with 7 .tf files
    2. versions.tf requires google provider >= 5.0.0
    3. variables.tf contains 15+ variable definitions with descriptions
    4. validation rules present for project_id (regex), region (allowed list), machine_type (allowed list)
    5. .gitignore excludes .terraform/, *.tfstate, *.tfvars
    6. terraform init succeeds and downloads providers
  - test scenario(s):
    - **scenario: initialize terraform**
      - steps: cd terraform/gcp → terraform init
      - expected result: providers downloaded, .terraform directory created, no errors
      - evidence: [placeholder for init output]
    - **scenario: validate variable constraints**
      - steps: create terraform.tfvars with invalid region "invalid-region" → terraform validate
      - expected result: validation error for region variable
      - evidence: [placeholder for validation error]
  - owner: infrastructure engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase2:2.1): create terraform GCP directory structure and base files
    - record commit sha in evidence link

- **task 2.2: implement VPC networking (vpc.tf)**
  - description: create vpc.tf defining VPC network, public and private subnets with secondary IP ranges for GKE pods and services (VPC-native cluster requirement), Cloud Router, and Cloud NAT for private subnet egress. configure subnet IP ranges: primary 10.0.0.0/20 (nodes), secondary 10.4.0.0/14 (pods), secondary 10.0.16.0/20 (services). enable private Google access on private subnet for GCP API access without public IPs. configure Cloud NAT to use automatic IP allocation.
  - acceptance criteria:
    1. google_compute_network resource created with auto_create_subnetworks=false
    2. google_compute_subnetwork for private nodes with 3 IP range configurations
    3. google_compute_router resource in specified region
    4. google_compute_router_nat resource with nat_ip_allocate_option="AUTO_ONLY"
    5. private_ip_google_access enabled on private subnet
    6. IP ranges sized appropriately (10.4.0.0/14 provides 262k pod IPs)
  - test scenario(s):
    - **scenario: plan VPC resources**
      - steps: terraform plan → review planned VPC resources
      - expected result: 4 resources planned (network, subnet, router, nat), no errors
      - evidence: [placeholder for plan output]
    - **scenario: verify IP range sizing**
      - steps: inspect subnet configuration → calculate available IPs
      - expected result: pod range provides 250k+ addresses, service range provides 4k addresses
      - evidence: [placeholder for IP calculation]
  - owner: infrastructure engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase2:2.2): implement VPC networking with Cloud NAT
    - record commit sha in evidence link

- **task 2.3: create service accounts and IAM bindings (iam.tf)**
  - description: create iam.tf defining three google_service_account resources (gke-cluster, gke-nodes, n8n-workload) and corresponding IAM role bindings. cluster SA gets roles/container.serviceAgent and roles/compute.networkUser. node SA gets roles/logging.logWriter, roles/monitoring.metricWriter, roles/storage.objectViewer. workload SA gets roles/secretmanager.secretAccessor and roles/cloudsql.client (if Cloud SQL enabled). implement conditional IAM binding based on database_type variable.
  - acceptance criteria:
    1. three google_service_account resources created
    2. google_project_iam_member resources created for each SA-role binding
    3. cluster SA has exactly 2 role bindings
    4. node SA has exactly 3 role bindings
    5. workload SA has 1-2 role bindings (conditional on database_type)
    6. service account emails output for workload identity binding
  - test scenario(s):
    - **scenario: plan IAM resources for SQLite config**
      - steps: set database_type="sqlite" → terraform plan → count IAM resources
      - expected result: 3 service accounts + 6 role bindings (no cloudsql.client)
      - evidence: [placeholder for plan count]
    - **scenario: plan IAM resources for Cloud SQL config**
      - steps: set database_type="cloudsql" → terraform plan → count IAM resources
      - expected result: 3 service accounts + 7 role bindings (includes cloudsql.client)
      - evidence: [placeholder for plan count]
  - owner: infrastructure engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase2:2.3): create GKE service accounts with minimal IAM roles
    - record commit sha in evidence link

- **task 2.4: implement GKE cluster and node pool (gke.tf)**
  - description: create gke.tf defining google_container_cluster resource for regional GKE cluster with workload identity enabled, VPC-native networking, private nodes, and network policy enabled. configure initial node pool with machine type from variable, autoscaling disabled (fixed node count), and node service account. enable cluster addons: http_load_balancing, horizontal_pod_autoscaling, network_policy_config. set release channel to REGULAR. configure maintenance window and master authorized networks (allow all for initial implementation).
  - acceptance criteria:
    1. google_container_cluster resource in regional mode (location = region)
    2. workload_identity_config enabled with workload pool
    3. ip_allocation_policy configured with secondary ranges from VPC
    4. private_cluster_config with enable_private_nodes=true
    5. network_policy enabled with provider=CALICO
    6. node_pool with node_count from variable, no autoscaling
    7. cluster version set to latest stable (no specific version pin)
    8. estimated creation time: 15-20 minutes
  - test scenario(s):
    - **scenario: plan GKE cluster**
      - steps: terraform plan → review cluster configuration
      - expected result: 1 cluster resource, workload identity enabled, private nodes enabled
      - evidence: [placeholder for cluster plan details]
    - **scenario: verify node pool configuration**
      - steps: inspect node_pool block → check machine_type and node_count
      - expected result: machine_type=var.node_machine_type, initial_node_count=var.node_count
      - evidence: [placeholder for node pool config]
  - owner: infrastructure engineer
  - estimate: 5 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase2:2.4): implement GKE cluster with workload identity
    - record commit sha in evidence link

- **task 2.5: implement Secret Manager resources (secrets.tf)**
  - description: create secrets.tf defining google_secret_manager_secret resources for n8n encryption key and basic auth credentials. generate random encryption key using random_password resource (32 chars, special chars). create google_secret_manager_secret_version resources to store secret values. configure IAM policy on secrets to grant workload SA access. implement lifecycle rule to prevent accidental deletion of secrets.
  - acceptance criteria:
    1. random_password resource generates 32-character encryption key
    2. google_secret_manager_secret for "n8n-encryption-key" created
    3. google_secret_manager_secret_version stores encryption key value
    4. google_secret_manager_secret_iam_member grants secretAccessor to workload SA
    5. lifecycle prevent_destroy=true on secret resources
    6. encryption key value available via terraform output (sensitive)
  - test scenario(s):
    - **scenario: plan Secret Manager resources**
      - steps: terraform plan → review secret resources
      - expected result: 2 secrets, 2 versions, 1 IAM binding planned
      - evidence: [placeholder for secrets plan]
    - **scenario: verify encryption key generation**
      - steps: terraform apply → retrieve output → check key length and character set
      - expected result: key is 32 chars, contains alphanumeric and special chars
      - evidence: [placeholder for key validation]
  - owner: infrastructure engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase2:2.5): implement Secret Manager for encryption keys
    - record commit sha in evidence link

- **task 2.6: implement Cloud SQL PostgreSQL (cloudsql.tf)**
  - description: create cloudsql.tf with conditional resources based on database_type variable. define google_sql_database_instance with tier from variable (db-f1-micro default), PostgreSQL 15, private IP only (no public IP), authorized network referencing VPC. create google_sql_database for n8n database. create google_sql_user for n8n user with generated password. configure backup settings (enabled, 7-day retention). implement deletion protection flag (must be disabled before destroy). configure maintenance window.
  - acceptance criteria:
    1. resources created only when var.database_type == "cloudsql"
    2. google_sql_database_instance in specified region with private IP
    3. database version = "POSTGRES_15"
    4. instance tier = var.cloudsql_tier
    5. backup configuration enabled with point-in-time recovery
    6. deletion_protection = true (must be manually disabled before destroy)
    7. instance connection name output for Cloud SQL proxy
  - test scenario(s):
    - **scenario: plan with Cloud SQL enabled**
      - steps: set database_type="cloudsql" → terraform plan
      - expected result: 3 Cloud SQL resources planned (instance, database, user)
      - evidence: [placeholder for Cloud SQL plan]
    - **scenario: plan with Cloud SQL disabled**
      - steps: set database_type="sqlite" → terraform plan
      - expected result: 0 Cloud SQL resources planned
      - evidence: [placeholder for no Cloud SQL resources]
    - **scenario: verify private IP configuration**
      - steps: apply Cloud SQL config → inspect instance → check IP settings
      - expected result: private IP assigned, no public IP
      - evidence: [placeholder for IP configuration]
  - owner: infrastructure engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase2:2.6): implement conditional Cloud SQL PostgreSQL
    - record commit sha in evidence link

- **task 2.7: implement terraform outputs (outputs.tf)**
  - description: create outputs.tf with all required outputs for kubectl configuration and helm deployment. output configure_kubectl as gcloud command string, cluster_name, cluster_endpoint, n8n_encryption_key_value (sensitive), database_type, cloudsql_connection_name (conditional), cloudsql_database_name (conditional), cloudsql_username (conditional), cloudsql_password (sensitive, conditional), workload_identity_sa_email, vpc_network_name, private_subnet_name. format outputs to match AWS/Azure patterns for consistency in setup.py consumption.
  - acceptance criteria:
    1. outputs.tf contains 13 output definitions
    2. configure_kubectl output formatted as valid gcloud command
    3. sensitive outputs marked with sensitive=true
    4. conditional outputs use terraform conditional expressions
    5. all outputs have descriptions
    6. terraform output command succeeds after apply
  - test scenario(s):
    - **scenario: verify outputs after SQLite deployment**
      - steps: apply with database_type="sqlite" → terraform output -json → parse JSON
      - expected result: database_type="sqlite", Cloud SQL outputs null, encryption key present
      - evidence: [placeholder for output JSON]
    - **scenario: verify outputs after Cloud SQL deployment**
      - steps: apply with database_type="cloudsql" → terraform output → check Cloud SQL values
      - expected result: cloudsql_connection_name populated, cloudsql_database_name="n8n"
      - evidence: [placeholder for Cloud SQL outputs]
  - owner: infrastructure engineer
  - estimate: 2 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase2:2.7): implement terraform outputs for kubectl and helm
    - record commit sha in evidence link

- **task 2.8: create terraform documentation and examples**
  - description: create README.md in terraform/gcp with usage instructions, variable descriptions, example terraform.tfvars configurations for SQLite and Cloud SQL scenarios, and troubleshooting section. create terraform.tfvars.example with commented variables and sensible defaults. document estimated deployment time (22-25 minutes) and cost ($169/month for SQLite, $212/month for Cloud SQL). include architecture diagram (ASCII or link to diagram).
  - acceptance criteria:
    1. README.md contains sections: overview, prerequisites, usage, variables, outputs, examples, troubleshooting
    2. terraform.tfvars.example has all variables with comments and defaults
    3. cost estimates match gcp-requirements.md ($169 SQLite, $212 Cloud SQL)
    4. troubleshooting section covers common errors (API not enabled, insufficient permissions)
    5. example commands for init, plan, apply, destroy included
  - test scenario(s):
    - **scenario: follow README to deploy**
      - steps: new user reads README → copies tfvars.example → follows steps → deploys cluster
      - expected result: deployment succeeds following only README instructions
      - evidence: [placeholder for user test notes]
  - owner: technical writer / infrastructure engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: docs(phase2:2.8): add terraform documentation and examples
    - record commit sha in evidence link

- **task 2.9: integration test terraform deployment**
  - description: execute full terraform deployment in test GCP project across three regions (us-central1, us-east1, europe-west1) for both SQLite and Cloud SQL configurations (6 total deployments). verify all resources created successfully, kubectl access works, workload identity binding functional, Cloud NAT provides egress, Cloud SQL connectivity (if enabled), and terraform destroy cleans up completely. document test results with resource counts, deployment times, and any issues encountered.
  - acceptance criteria:
    1. 6 test deployments execute successfully (3 regions × 2 database types)
    2. average deployment time ≤ 25 minutes per deployment
    3. kubectl get nodes shows READY status for all nodes
    4. workload identity test pod accesses Secret Manager successfully
    5. Cloud NAT egress test succeeds from private pod
    6. Cloud SQL connectivity test succeeds (for Cloud SQL deployments)
    7. terraform destroy completes cleanly with 0 resources remaining
    8. test results documented with screenshots and logs
  - test scenario(s):
    - **scenario: full deployment us-central1 SQLite**
      - steps: create tfvars → terraform apply → verify cluster → kubectl test → terraform destroy
      - expected result: deployment time < 25 min, all tests pass, destroy clean
      - evidence: [placeholder for deployment log and timing]
    - **scenario: full deployment us-east1 Cloud SQL**
      - steps: create tfvars with Cloud SQL → terraform apply → verify cluster and database → test connectivity → terraform destroy
      - expected result: Cloud SQL instance running, pod connects via private IP, destroy clean
      - evidence: [placeholder for Cloud SQL test]
    - **scenario: workload identity verification**
      - steps: deploy test pod with SA annotation → pod reads secret → check logs
      - expected result: secret value retrieved successfully
      - evidence: [placeholder for pod logs]
  - owner: infrastructure engineer + QA engineer
  - estimate: 8 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA and test report]
  - git actions (end of task):
    - commit: yes
    - suggested message: test(phase2:2.9): integration test terraform across 3 regions
    - record commit sha in evidence link

### risks and mitigations

- **risk: GKE cluster creation times exceed 25 minutes causing user frustration** → **mitigation:** document expected wait time clearly; implement progress indicators in setup.py; consider zonal clusters for faster creation (trade-off: reduced HA)
- **risk: Cloud SQL private IP requires VPC peering that may conflict with existing peerings** → **mitigation:** document VPC peering limits (25 per VPC); provide error handling for peering conflicts; consider Cloud SQL proxy as alternative
- **risk: terraform state file corruption or loss** → **mitigation:** implement GCS backend for state storage; enable versioning on state bucket; document state recovery procedures
- **risk: workload identity misconfiguration prevents pod access to Secret Manager** → **mitigation:** create detailed troubleshooting guide; implement validation checks in terraform outputs; provide test pod manifest
- **risk: IP range exhaustion in VPC-native clusters** → **mitigation:** use large secondary ranges (/14 for pods); document IP planning in README; implement validation for IP range sizing
- **risk: terraform provider version incompatibility** → **mitigation:** pin provider versions in versions.tf; test with google provider 5.0, 5.10, 5.20; document tested versions

### dependencies

- GCP test project with billing enabled
- terraform 1.6+ installed
- gcloud CLI authenticated
- required GCP APIs enabled (compute, container, secretmanager, sqladmin)
- phase 1 completion (configuration classes available for testing)

### completion checklist (exit criteria)

- [ ] all phase-level acceptance criteria met
- [ ] all task test scenarios passed
- [ ] uat executed and recorded
- [ ] documentation updated (links)
- [ ] phase commit created and pushed (sha recorded)
- [ ] 6 integration test deployments successful
- [ ] README.md reviewed and approved
- [ ] no terraform plan warnings or errors
- [ ] all outputs tested and validated

### git actions (end of phase)

- create a commit summarizing the phase completion
- push to the remote repository
- record branch and commit sha

### phase execution report

*(fill after execution)*

- **what was done:**
  - tasks completed with links and evidence

- **test results summary:**
  - scenarios run: 0
  - pass: 0
  - fail: 0
  - defects found: 0 (links)

- **challenges encountered:**
  - description and how each was handled

- **learnings:**
  - key takeaways and recommendations

- **decision:**
  - go/no-go and rationale

- **git evidence:**
  - task commits: list shas
  - phase commit and push: branch and sha

- **next phase readiness:**
  - entry criteria confirmed

---

## phase 3 – deployment automation and helm integration

### outcome (what success looks like)

this phase delivers end-to-end GCP deployment automation within setup.py, enabling users to deploy n8n on GKE using `python3 setup.py --cloud-provider gcp` with the same experience as AWS/Azure. the implementation includes terraform integration functions (deploy_gcp_terraform), helm deployment functions (deploy_gcp_helm), main function routing for GCP cloud provider selection, FileUpdater methods for terraform.tfvars generation, and 4-phase deployment workflow (infrastructure, application, LoadBalancer URL, TLS/basic auth). by the end of this phase, a complete deployment from configuration collection to running n8n instance completes in under 35 minutes with comprehensive error handling and user feedback.

### scope (in)

- deploy_gcp_terraform function with terraform wrapper integration
- deploy_gcp_helm function with Cloud SQL proxy sidecar support
- FileUpdater.create_terraform_tfvars_gcp method
- main function GCP routing (deployment and teardown branches)
- kubectl configuration via gcloud command execution
- LoadBalancer URL retrieval with GCP-specific service query
- workload identity binding implementation
- Cloud SQL connectivity configuration (proxy or private IP)
- 4-phase deployment progress indicators
- error handling for common GCP failures
- configuration state management (save/restore region-specific state)

### negative scope (out)

- TLS configuration (Let's Encrypt integration deferred to phase 4)
- basic authentication configuration (deferred to phase 4)
- GKE autopilot support
- multi-cluster deployments
- automated DNS record creation (manual CNAME setup required)
- GCP marketplace integration

### deliverables

- deploy_gcp_terraform function in setup.py (~150 lines)
- deploy_gcp_helm function in setup.py (~200 lines)
- create_terraform_tfvars_gcp method in FileUpdater class (~80 lines)
- GCP deployment flow in main function (~250 lines)
- kubectl configuration helper functions
- Cloud SQL proxy sidecar injection logic
- workload identity annotation helper
- updated --cloud-provider argument to accept 'gcp'
- updated cloud provider selection prompt (3 options)
- GCP-specific error messages and troubleshooting hints
- integration test script for full deployment workflow

### acceptance criteria (phase-level)

1. `python3 setup.py --cloud-provider gcp` completes full deployment successfully
2. deployment creates GKE cluster, node pool, VPC, Secret Manager secrets, and n8n pods
3. n8n pod status transitions to "Running" within 5 minutes of helm install
4. LoadBalancer external IP is retrieved and displayed to user
5. n8n UI accessible via LoadBalancer URL (HTTP, port 80)
6. Cloud SQL proxy sidecar (if Cloud SQL selected) successfully connects to database
7. workload identity binding allows pod to read Secret Manager encryption key
8. terraform state saved with region-specific naming (terraform.tfstate.{region}.backup)
9. configuration saved to setup_history.log with GCP provider tag
10. deployment completion message displays kubectl commands and LoadBalancer URL

### uat (user acceptance tests)

- **scenario: complete GCP deployment with SQLite**
  - steps: run `python3 setup.py --cloud-provider gcp` → select project → choose SQLite → confirm terraform plan → wait for completion → verify LoadBalancer URL → access n8n UI
  - expected result: deployment completes in < 30 min, n8n UI loads at LoadBalancer URL, no errors
  - evidence: [placeholder for deployment log and n8n UI screenshot]

- **scenario: complete GCP deployment with Cloud SQL**
  - steps: run `python3 setup.py --cloud-provider gcp` → select Cloud SQL → provide instance details → complete deployment → check pod logs for database connection
  - expected result: Cloud SQL instance created, n8n pod logs show "connected to PostgreSQL", workflows can be saved
  - evidence: [placeholder for pod logs showing DB connection]

- **scenario: verify workload identity in deployed pod**
  - steps: after deployment → kubectl exec into n8n pod → attempt to read Secret Manager secret using application default credentials
  - expected result: secret value retrieved without error, proving workload identity works
  - evidence: [placeholder for kubectl exec output]

- **scenario: LoadBalancer URL retrieval**
  - steps: during deployment → observe Phase 3 output → verify external IP displayed → curl LoadBalancer URL
  - expected result: external IP shown in green text, curl returns n8n login page HTML
  - evidence: [placeholder for curl output]

- **scenario: multi-region deployment state management**
  - steps: deploy to us-central1 → deploy to us-east1 → verify separate state files → restore us-central1 state → teardown us-central1
  - expected result: two state backups exist, state restore works, teardown targets correct region
  - evidence: [placeholder for state file listing]

### tasks

- **task 3.1: implement deploy_gcp_terraform function**
  - description: create deploy_gcp_terraform(config, terraform_dir) function that orchestrates terraform deployment. initialize TerraformRunner with terraform/gcp directory, run terraform init, execute terraform plan with detailed output, prompt user for confirmation, run terraform apply with progress indicators, configure kubectl using gcloud command from outputs, save terraform state with region-specific naming, return boolean success status. implement error handling for common terraform failures (API not enabled, quota exceeded, authentication expired).
  - acceptance criteria:
    1. function accepts GCPDeploymentConfig and Path parameters
    2. terraform init called and verified successful
    3. terraform plan output displayed to user with resource count
    4. user confirmation required before apply (yes/no prompt)
    5. terraform apply executes with real-time output streaming
    6. kubectl configured via `gcloud container clusters get-credentials` command
    7. terraform state saved to terraform.tfstate.{region}.backup
    8. function returns True on success, False on any failure
    9. error messages include actionable troubleshooting hints
  - test scenario(s):
    - **scenario: successful terraform deployment**
      - steps: call deploy_gcp_terraform with valid config → mock terraform success → verify kubectl configuration
      - expected result: function returns True, kubectl context set, state file saved
      - evidence: [placeholder for function output]
    - **scenario: handle terraform apply failure**
      - steps: call function → simulate terraform apply error → verify error handling
      - expected result: function returns False, error message displayed, no state corruption
      - evidence: [placeholder for error handling]
    - **scenario: user cancels terraform apply**
      - steps: call function → terraform plan succeeds → user responds "no" to confirmation
      - expected result: function exits gracefully, SetupInterrupted exception raised
      - evidence: [placeholder for cancellation flow]
  - owner: backend engineer
  - estimate: 6 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase3:3.1): implement deploy_gcp_terraform with error handling
    - record commit sha in evidence link

- **task 3.2: implement Cloud SQL proxy sidecar injection**
  - description: create helper function inject_cloudsql_proxy(config, namespace) that patches n8n deployment to add Cloud SQL proxy sidecar container when database_type="cloudsql". sidecar container uses gcr.io/cloudsql-docker/gce-proxy:latest image, runs proxy command with instance connection name from config, exposes port 5432 internally, shares no volumes (proxy handles connectivity). implement kubectl patch command to inject sidecar. configure n8n container to connect to 127.0.0.1:5432 (localhost via shared pod network).
  - acceptance criteria:
    1. function executes only when config.database_type == "cloudsql"
    2. kubectl patch deployment command constructed correctly
    3. sidecar container definition includes correct image and command
    4. sidecar command references config.cloudsql_connection_name
    5. n8n container DATABASE_HOST set to 127.0.0.1
    6. n8n container DATABASE_PORT set to 5432
    7. pod restart triggers after patch to apply sidecar
    8. pod logs show Cloud SQL proxy startup messages
  - test scenario(s):
    - **scenario: inject Cloud SQL proxy into deployment**
      - steps: call function with Cloud SQL config → verify deployment patched → check pod spec
      - expected result: deployment has 2 containers (n8n + cloud-sql-proxy), proxy logs show "ready for connections"
      - evidence: [placeholder for kubectl get deployment output]
    - **scenario: verify proxy connectivity**
      - steps: after injection → kubectl exec into n8n container → nc -zv 127.0.0.1 5432
      - expected result: connection to localhost:5432 succeeds, proving proxy works
      - evidence: [placeholder for connectivity test]
  - owner: backend engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase3:3.2): implement Cloud SQL proxy sidecar injection
    - record commit sha in evidence link

- **task 3.3: implement workload identity binding**
  - description: create function configure_workload_identity(config, namespace) that binds Kubernetes service account to Google service account for workload identity. create Kubernetes SA if not exists (`kubectl create sa n8n-sa -n {namespace}`), annotate SA with iam.gke.io/gcp-service-account={workload_sa_email}, grant workloadIdentityUser role to Kubernetes SA (`gcloud iam service-accounts add-iam-policy-binding`), patch n8n deployment to use Kubernetes SA (spec.serviceAccountName). verify binding by deploying test pod that accesses Secret Manager.
  - acceptance criteria:
    1. Kubernetes service account "n8n-sa" created in n8n namespace
    2. annotation iam.gke.io/gcp-service-account added with correct Google SA email
    3. gcloud iam command grants roles/iam.workloadIdentityUser to serviceAccount:{project}.svc.id.goog[{namespace}/n8n-sa]
    4. n8n deployment spec.serviceAccountName = "n8n-sa"
    5. test pod with workload identity successfully reads Secret Manager secret
    6. binding verified via `gcloud iam service-accounts get-iam-policy`
  - test scenario(s):
    - **scenario: configure workload identity**
      - steps: call function → verify SA created → verify annotation → verify IAM binding
      - expected result: all steps complete without error, workload identity operational
      - evidence: [placeholder for kubectl and gcloud outputs]
    - **scenario: test workload identity with pod**
      - steps: deploy test pod → pod reads secret from Secret Manager → check success
      - expected result: pod retrieves secret value without errors
      - evidence: [placeholder for test pod logs]
  - owner: backend engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase3:3.3): implement GKE workload identity binding
    - record commit sha in evidence link

- **task 3.4: implement deploy_gcp_helm function**
  - description: create deploy_gcp_helm(config, charts_dir, encryption_key) function that deploys n8n via Helm with GCP-specific configuration. prepare database configuration dictionary from config (database_type, Cloud SQL connection details if applicable), create Kubernetes secret for database credentials if Cloud SQL, deploy n8n using HelmRunner.deploy_n8n with db_config parameter, inject Cloud SQL proxy sidecar if Cloud SQL enabled, configure workload identity binding, verify deployment status (wait for pods Running), return boolean success status. implement retries for pod readiness checks (max 10 attempts, 30-second intervals).
  - acceptance criteria:
    1. function accepts GCPDeploymentConfig, Path, and encryption_key string
    2. database credentials secret created if database_type="cloudsql"
    3. helm install n8n command executed with correct values
    4. Cloud SQL proxy injected if database_type="cloudsql"
    5. workload identity binding configured for n8n service account
    6. pod status checked with retries (max 5 minutes wait)
    7. function returns True when pods reach Running status
    8. function returns False if pods fail to start after retries
  - test scenario(s):
    - **scenario: deploy n8n with SQLite**
      - steps: call function with SQLite config → verify helm install → check pod status
      - expected result: deployment created, pod Running, no Cloud SQL proxy
      - evidence: [placeholder for helm list and kubectl get pods]
    - **scenario: deploy n8n with Cloud SQL**
      - steps: call function with Cloud SQL config → verify secret creation → verify proxy injection → check connectivity
      - expected result: secret exists, pod has 2 containers, database connection succeeds
      - evidence: [placeholder for pod describe output]
  - owner: backend engineer
  - estimate: 6 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase3:3.4): implement deploy_gcp_helm with Cloud SQL support
    - record commit sha in evidence link

- **task 3.5: implement create_terraform_tfvars_gcp method**
  - description: add create_terraform_tfvars_gcp(config) method to FileUpdater class that generates terraform/gcp/terraform.tfvars file from GCPDeploymentConfig object. write terraform variable assignments for all configuration parameters (project_id, region, zone, cluster_name, node_machine_type, node_count, database_type, cloudsql_tier, n8n_host, etc.). format file with proper HCL syntax (key = "value"). include header comment with timestamp and warning about auto-generation. verify file is valid HCL by running terraform validate after creation.
  - acceptance criteria:
    1. method creates terraform/gcp/terraform.tfvars file
    2. file contains 15+ variable assignments matching config attributes
    3. HCL syntax is valid (terraform validate passes)
    4. file header includes timestamp and generation warning
    5. string values properly quoted, numbers unquoted, booleans lowercase (true/false)
    6. database_type and cloudsql_* variables set correctly based on config
  - test scenario(s):
    - **scenario: generate tfvars for SQLite config**
      - steps: call method with SQLite config → read generated file → verify variables
      - expected result: database_type = "sqlite", no cloudsql_* variables
      - evidence: [placeholder for tfvars file content]
    - **scenario: generate tfvars for Cloud SQL config**
      - steps: call method with Cloud SQL config → read file → verify Cloud SQL vars
      - expected result: database_type = "cloudsql", cloudsql_tier = "db-f1-micro"
      - evidence: [placeholder for tfvars file content]
    - **scenario: validate generated HCL**
      - steps: generate tfvars → cd terraform/gcp → terraform validate
      - expected result: validation passes with no errors
      - evidence: [placeholder for validate output]
  - owner: backend engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase3:3.5): implement terraform tfvars generation for GCP
    - record commit sha in evidence link

- **task 3.6: integrate GCP deployment flow into main function**
  - description: modify main() function to add GCP deployment branch after Azure deployment section (around line 3876). implement GCP deployment flow following AWS/Azure patterns: prompt for cloud provider (add GCP as option 3), collect GCP configuration via ConfigurationPrompt.collect_gcp_configuration, save configuration to history via ConfigHistoryManager, create terraform tfvars via FileUpdater, execute deploy_gcp_terraform (Phase 1), execute deploy_gcp_helm (Phase 2), retrieve LoadBalancer URL (Phase 3), display completion message with access instructions, skip TLS/basic auth configuration (placeholder for phase 4). implement proper exception handling with SetupInterrupted support.
  - acceptance criteria:
    1. cloud provider selection prompt displays 3 options (AWS, Azure, GCP)
    2. selecting GCP routes to GCP deployment flow
    3. all 4 phases execute in sequence with progress indicators
    4. Phase 1 displays infrastructure deployment message (estimated 22-25 min)
    5. Phase 2 displays n8n application deployment message
    6. Phase 3 retrieves and displays LoadBalancer URL
    7. completion message shows kubectl commands and access URL
    8. errors are caught and displayed with helpful messages
    9. configuration saved to setup_history.log before terraform runs
  - test scenario(s):
    - **scenario: select GCP from provider menu**
      - steps: run setup.py → observe menu → select option 3 (GCP)
      - expected result: GCP deployment flow starts, configuration prompts appear
      - evidence: [placeholder for menu screenshot]
    - **scenario: complete 4-phase deployment**
      - steps: select GCP → complete config → observe phase messages → verify completion
      - expected result: Phase 1-3 execute with progress indicators, completion message displayed
      - evidence: [placeholder for phase output screenshots]
    - **scenario: handle deployment error gracefully**
      - steps: simulate terraform failure → observe error handling
      - expected result: error message displayed, program exits cleanly
      - evidence: [placeholder for error message]
  - owner: backend engineer
  - estimate: 5 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase3:3.6): integrate GCP deployment into main function
    - record commit sha in evidence link

- **task 3.7: implement GCP teardown routing in main function**
  - description: add GCP teardown branch to main() function's teardown section (around line 3583). detect GCP configuration from terraform/gcp/terraform.tfvars, parse project_id and region, instantiate GCPDeploymentConfig, display teardown configuration summary, route to GKETeardown.execute() (stub implementation for now, full implementation in phase 4), handle errors and exit codes. implement configuration detection logic similar to AWS/Azure teardown patterns.
  - acceptance criteria:
    1. elif cloud_provider == "gcp": branch added to teardown section
    2. terraform/gcp/terraform.tfvars parsed for configuration
    3. GCPDeploymentConfig instantiated with detected values
    4. teardown configuration displayed (project ID, region, cluster name)
    5. GKETeardown class instantiated (stub returns True for now)
    6. exit code 0 on success, 1 on failure
  - test scenario(s):
    - **scenario: route GCP teardown**
      - steps: run `python3 setup.py --cloud-provider gcp --teardown` → verify routing
      - expected result: GCP teardown branch executes, config displayed, stub teardown called
      - evidence: [placeholder for teardown output]
  - owner: backend engineer
  - estimate: 2 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase3:3.7): add GCP teardown routing to main function
    - record commit sha in evidence link

- **task 3.8: implement LoadBalancer URL retrieval for GCP**
  - description: create get_gcp_loadbalancer_url(namespace, max_attempts, delay) function that retrieves external IP from LoadBalancer service in GCP. query ingress-nginx-controller service using kubectl, extract LoadBalancer IP from status.loadBalancer.ingress[0].ip (GCP uses IP, not hostname like AWS), retry up to max_attempts times with delay between attempts, return IP string or None if not available. handle pending state gracefully with informative messages.
  - acceptance criteria:
    1. function queries kubectl for service in ingress-nginx namespace
    2. extracts IP from JSON output using jsonpath
    3. retries up to max_attempts (default 30) with delay (default 10s)
    4. returns IP string (e.g., "34.56.78.90") when available
    5. returns None if LoadBalancer pending after all retries
    6. displays retry progress to user ("Waiting for LoadBalancer... attempt 1/30")
  - test scenario(s):
    - **scenario: retrieve LoadBalancer IP successfully**
      - steps: deploy cluster with LoadBalancer → call function → verify IP returned
      - expected result: function returns valid IP address string
      - evidence: [placeholder for IP output]
    - **scenario: handle LoadBalancer pending**
      - steps: call function before LoadBalancer ready → observe retries → timeout
      - expected result: function retries, displays progress, returns None after max attempts
      - evidence: [placeholder for retry messages]
  - owner: backend engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase3:3.8): implement LoadBalancer URL retrieval for GCP
    - record commit sha in evidence link

- **task 3.9: end-to-end integration testing**
  - description: execute complete end-to-end deployment workflow using setup.py GCP integration across 3 test scenarios: (1) us-central1 with SQLite, (2) us-east1 with Cloud SQL, (3) europe-west1 with SQLite. measure deployment times, verify all phases execute correctly, test n8n UI accessibility via LoadBalancer, verify workload identity by checking pod can access secrets, verify Cloud SQL connectivity for scenario 2, test state management (deploy to 2 regions, restore state, teardown 1 region). document all test results, screenshots, timing data, and any issues encountered.
  - acceptance criteria:
    1. 3 test deployments complete successfully (100% success rate)
    2. average deployment time ≤ 35 minutes (infrastructure + application + LB)
    3. n8n UI accessible via LoadBalancer IP for all 3 deployments
    4. workload identity verified (pod reads Secret Manager secret)
    5. Cloud SQL connectivity verified for us-east1 deployment
    6. state management tested (multi-region deployment and teardown)
    7. comprehensive test report created with evidence links
    8. all test environments cleaned up (terraform destroy verified)
  - test scenario(s):
    - **scenario: us-central1 SQLite deployment**
      - steps: run setup.py → select GCP → configure SQLite → complete deployment → access UI → verify pod logs
      - expected result: deployment < 30 min, n8n UI accessible, encryption key loaded from Secret Manager
      - evidence: [placeholder for deployment log, UI screenshot, pod logs]
    - **scenario: us-east1 Cloud SQL deployment**
      - steps: run setup.py → select Cloud SQL → complete deployment → verify database connection → test workflow save
      - expected result: Cloud SQL proxy running, database connection successful, workflows persist
      - evidence: [placeholder for Cloud SQL test results]
    - **scenario: multi-region state management**
      - steps: deploy us-central1 → deploy europe-west1 → list state files → restore us-central1 → teardown us-central1
      - expected result: 2 state backups created, restore works, teardown targets correct region
      - evidence: [placeholder for state management test]
  - owner: backend engineer + QA engineer
  - estimate: 8 h
  - status: [ ] todo
  - evidence link: [placeholder for test report and commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: test(phase3:3.9): end-to-end integration testing across 3 regions
    - record commit sha in evidence link

### risks and mitigations

- **risk: LoadBalancer IP allocation failures in certain GCP regions** → **mitigation:** implement comprehensive error messages; test in 3 regions; provide fallback to manual IP reservation
- **risk: Cloud SQL proxy sidecar causes pod startup delays** → **mitigation:** configure liveness/readiness probes with longer initial delays; document expected startup time (2-3 min)
- **risk: workload identity binding race condition (pod starts before binding complete)** → **mitigation:** implement binding verification before helm install; add retry logic to pod startup
- **risk: terraform state corruption during multi-region deployments** → **mitigation:** implement robust state save/restore with validation; use GCS backend for state locking
- **risk: kubectl configuration conflicts with existing clusters** → **mitigation:** implement context switching logic; verify correct cluster before operations; document manual context commands
- **risk: deployment time exceeds user expectations** → **mitigation:** display realistic time estimates; show progress indicators; implement timeout handling

### dependencies

- phase 1 completed (GCP configuration classes available)
- phase 2 completed (terraform modules deployed and tested)
- HelmRunner class functional with existing n8n chart
- TerraformRunner class functional with terraform wrapper
- kubectl installed and functional on deployment machine

### completion checklist (exit criteria)

- [ ] all phase-level acceptance criteria met
- [ ] all task test scenarios passed
- [ ] uat executed and recorded
- [ ] documentation updated (links)
- [ ] phase commit created and pushed (sha recorded)
- [ ] 3 end-to-end deployments successful
- [ ] LoadBalancer accessibility verified in all test regions
- [ ] workload identity verified functional
- [ ] Cloud SQL connectivity verified
- [ ] state management tested across regions
- [ ] test report completed with evidence

### git actions (end of phase)

- create a commit summarizing the phase completion
- push to the remote repository
- record branch and commit sha

### phase execution report

*(fill after execution)*

- **what was done:**
  - tasks completed with links and evidence

- **test results summary:**
  - scenarios run: 0
  - pass: 0
  - fail: 0
  - defects found: 0 (links)

- **challenges encountered:**
  - description and how each was handled

- **learnings:**
  - key takeaways and recommendations

- **decision:**
  - go/no-go and rationale

- **git evidence:**
  - task commits: list shas
  - phase commit and push: branch and sha

- **next phase readiness:**
  - entry criteria confirmed

---

## phase 4 – teardown, tls, and production readiness

### outcome (what success looks like)

this phase completes the GCP implementation by delivering production-grade features: comprehensive teardown functionality for clean resource cleanup, TLS certificate automation with Let's Encrypt, basic authentication configuration, and final polish for production deployments. by the end of this phase, the GCP implementation achieves feature parity with AWS and Azure, including full 4-phase teardown (helm, kubernetes, terraform, secrets), TLS configuration with automatic certificate issuance, basic auth credential management via Secret Manager, and comprehensive documentation. users can confidently deploy and teardown n8n on GKE with the same capabilities as existing cloud providers.

### scope (in)

- GKETeardown class with 4-phase teardown workflow
- TLS configuration integration (Let's Encrypt HTTP-01 challenge)
- basic authentication configuration with Secret Manager
- cert-manager deployment via Helm
- ClusterIssuer configuration for Let's Encrypt
- ingress TLS annotation updates
- Secret Manager integration for basic auth credentials
- --configure-tls flag support for GCP
- --restore-region flag support for GCP state management
- comprehensive error handling for teardown failures
- documentation updates (README.md, getting-started.md, gcp-requirements.md)
- final production readiness checklist

### negative scope (out)

- Let's Encrypt DNS-01 challenge (HTTP-01 only)
- custom TLS certificate upload beyond basic support
- advanced security features (Cloud Armor, Binary Authorization)
- automated DNS record creation
- GCP marketplace listing
- monitoring dashboard creation
- backup automation for persistent volumes

### deliverables

- GKETeardown class in setup.py (~400 lines)
- configure_tls_gcp function (~150 lines)
- configure_basic_auth_gcp function (~100 lines)
- cert-manager deployment helper
- Secret Manager basic auth integration
- updated main function with TLS/auth phases for GCP
- updated --restore-region support for GCP
- comprehensive teardown test suite
- updated README.md with GCP sections
- updated docs/getting-started.md
- updated docs/guides/gcp-requirements.md with deployment guide
- production deployment checklist
- troubleshooting guide for common GCP issues

### acceptance criteria (phase-level)

1. GKETeardown.execute() completes 4-phase teardown successfully
2. teardown removes all GCP resources (cluster, VPC, secrets, Cloud SQL)
3. terraform destroy completes without orphaned resources
4. TLS configuration deploys cert-manager and creates ClusterIssuer
5. Let's Encrypt certificate issued successfully and bound to ingress
6. n8n accessible via HTTPS with valid Let's Encrypt certificate
7. basic authentication configured with credentials stored in Secret Manager
8. basic auth prompts for username/password when accessing n8n UI
9. --configure-tls flag works for existing GCP deployments
10. --restore-region flag restores GCP terraform state correctly
11. all documentation updated with GCP content matching AWS/Azure depth
12. production deployment succeeds in real GCP environment (not test project)

### uat (user acceptance tests)

- **scenario: complete teardown of GCP deployment**
  - steps: deploy full GKE cluster → run `python3 setup.py --cloud-provider gcp --teardown` → confirm prompts → verify resource cleanup
  - expected result: all resources removed, GKE cluster deleted, VPC deleted, Secret Manager secrets deleted, no orphaned resources
  - evidence: [placeholder for teardown log and gcloud list outputs]

- **scenario: configure TLS with Let's Encrypt**
  - steps: deploy GKE cluster → configure DNS CNAME → run `python3 setup.py --cloud-provider gcp --configure-tls` → select Let's Encrypt → provide email → wait for certificate
  - expected result: cert-manager deployed, certificate issued, n8n accessible via HTTPS, browser shows valid certificate
  - evidence: [placeholder for certificate details and browser screenshot]

- **scenario: configure basic authentication**
  - steps: after deployment → run basic auth configuration → provide username/password → verify credentials saved → access n8n URL
  - expected result: browser prompts for basic auth, correct credentials grant access, incorrect credentials denied
  - evidence: [placeholder for auth prompt screenshot]

- **scenario: multi-region teardown with state restore**
  - steps: deploy us-central1 and us-east1 → run `python3 setup.py --cloud-provider gcp --restore-region us-central1 --teardown` → verify only us-central1 removed
  - expected result: us-central1 resources deleted, us-east1 resources untouched, state management works correctly
  - evidence: [placeholder for selective teardown results]

- **scenario: production deployment end-to-end**
  - steps: use production GCP project → deploy with Cloud SQL → configure TLS → configure basic auth → create test workflow → verify persistence
  - expected result: full production deployment functional, workflows persist across pod restarts, HTTPS and auth working
  - evidence: [placeholder for production deployment verification]

### tasks

- **task 4.1: implement GKETeardown class with 4-phase workflow**
  - description: create GKETeardown class following TeardownRunner (AWS) and AKSTeardown (Azure) patterns. implement execute() method with 4 phases: Phase 1 (uninstall helm releases: n8n, ingress-nginx, cert-manager), Phase 2 (delete kubernetes resources: PVCs, secrets, namespaces), Phase 3 (terraform destroy with auto-approve after confirmation), Phase 4 (delete Secret Manager secrets using gcloud). include user confirmation prompts, 5-second countdown, comprehensive progress indicators, error handling for partial failures, and rollback guidance. implement dry-run mode to show what would be deleted.
  - acceptance criteria:
    1. GKETeardown class has __init__(script_dir, config) and execute() methods
    2. execute() implements 4 sequential phases with clear phase headers
    3. user must confirm teardown before Phase 1 execution
    4. Phase 1 uninstalls 3 helm releases (n8n, ingress-nginx, cert-manager if exists)
    5. Phase 2 deletes PVCs, secrets, and 3 namespaces (n8n, ingress-nginx, cert-manager)
    6. Phase 3 runs terraform destroy in terraform/gcp directory
    7. Phase 4 deletes Secret Manager secrets using gcloud
    8. progress indicators show completion status for each phase
    9. errors in one phase don't prevent subsequent phases from attempting
    10. function returns True if all phases succeed, False otherwise
  - test scenario(s):
    - **scenario: complete teardown**
      - steps: deploy full GKE → instantiate GKETeardown → call execute() → observe phases
      - expected result: all 4 phases execute, all resources deleted, function returns True
      - evidence: [placeholder for teardown log]
    - **scenario: handle missing resources gracefully**
      - steps: manually delete some resources → run teardown → verify no errors for missing items
      - expected result: teardown completes successfully, missing resources logged but not errors
      - evidence: [placeholder for partial teardown log]
    - **scenario: user cancels teardown**
      - steps: call execute() → respond "no" to confirmation prompt
      - expected result: teardown aborts immediately, no resources deleted
      - evidence: [placeholder for cancellation message]
  - owner: backend engineer
  - estimate: 8 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase4:4.1): implement GKETeardown with 4-phase workflow
    - record commit sha in evidence link

- **task 4.2: implement cert-manager deployment for GCP**
  - description: create deploy_cert_manager_gcp(namespace) function that deploys cert-manager via Helm if not already installed. check for existing cert-manager installation, add cert-manager helm repo (jetstack), deploy cert-manager with CRDs, wait for cert-manager pods to be ready (max 3 minutes), verify cert-manager webhook is functional, return boolean success status. implement idempotency to avoid duplicate installations.
  - acceptance criteria:
    1. function checks for existing cert-manager namespace before installation
    2. helm repo add jetstack https://charts.jetstack.io executed
    3. helm install cert-manager with --set installCRDs=true
    4. cert-manager deployed to cert-manager namespace
    5. wait for 3 pods (cert-manager, webhook, cainjector) to be Ready
    6. webhook connectivity test passes
    7. function returns True on successful deployment
    8. function skips deployment if cert-manager already exists (returns True)
  - test scenario(s):
    - **scenario: deploy cert-manager first time**
      - steps: call function on clean cluster → verify deployment → check pod status
      - expected result: cert-manager installed, 3 pods Running, function returns True
      - evidence: [placeholder for helm list and pod status]
    - **scenario: detect existing cert-manager**
      - steps: deploy cert-manager → call function again → verify skip
      - expected result: function detects existing installation, returns True without redeploying
      - evidence: [placeholder for skip message]
  - owner: backend engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase4:4.2): implement cert-manager deployment for GCP
    - record commit sha in evidence link

- **task 4.3: implement ClusterIssuer creation for Let's Encrypt**
  - description: create create_letsencrypt_issuer(email, namespace, staging=False) function that creates ClusterIssuer custom resource for Let's Encrypt. construct ClusterIssuer YAML with ACME server URL (production or staging), email for notifications, private key secret name, HTTP-01 solver configuration with ingress class nginx. apply ClusterIssuer using kubectl. verify issuer readiness by checking status.conditions. implement staging mode for testing to avoid rate limits.
  - acceptance criteria:
    1. function generates valid ClusterIssuer YAML
    2. ACME server URL points to Let's Encrypt production (https://acme-v02.api.letsencrypt.org/directory)
    3. staging mode uses Let's Encrypt staging server when enabled
    4. HTTP-01 solver configured with ingressClass: nginx
    5. privateKeySecretRef name includes environment (letsencrypt-prod or letsencrypt-staging)
    6. kubectl apply -f executed successfully
    7. ClusterIssuer status shows Ready: True within 30 seconds
    8. function returns True on successful creation
  - test scenario(s):
    - **scenario: create production ClusterIssuer**
      - steps: call function with production email → verify ClusterIssuer created → check status
      - expected result: ClusterIssuer "letsencrypt-prod" created, status Ready
      - evidence: [placeholder for kubectl get clusterissuer output]
    - **scenario: create staging ClusterIssuer**
      - steps: call function with staging=True → verify staging server URL
      - expected result: ClusterIssuer uses staging server, ready for testing
      - evidence: [placeholder for staging issuer YAML]
  - owner: backend engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase4:4.3): implement Let's Encrypt ClusterIssuer creation
    - record commit sha in evidence link

- **task 4.4: implement TLS ingress configuration**
  - description: create configure_ingress_tls(config, namespace, issuer_name) function that updates n8n ingress to enable TLS with cert-manager annotations. add annotation cert-manager.io/cluster-issuer: {issuer_name}, add tls section to ingress spec with secretName: n8n-tls and hosts: [config.n8n_host], patch existing ingress using kubectl, verify certificate request created, wait for certificate to be issued (max 5 minutes), verify certificate Ready status, return boolean success status.
  - acceptance criteria:
    1. function patches existing n8n ingress resource
    2. annotation cert-manager.io/cluster-issuer added with correct issuer name
    3. spec.tls section added with secretName and hosts
    4. kubectl patch ingress command executed successfully
    5. cert-manager creates CertificateRequest automatically
    6. Certificate resource transitions to Ready: True state
    7. TLS secret "n8n-tls" created with valid certificate data
    8. function returns True when certificate ready
  - test scenario(s):
    - **scenario: configure TLS on existing ingress**
      - steps: call function with production issuer → wait for certificate → verify HTTPS access
      - expected result: ingress patched, certificate issued, HTTPS works
      - evidence: [placeholder for certificate status and curl HTTPS output]
    - **scenario: handle certificate issuance failure**
      - steps: provide invalid domain → attempt TLS config → observe error
      - expected result: certificate request fails, error message displayed with troubleshooting hints
      - evidence: [placeholder for failure handling]
  - owner: backend engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase4:4.4): implement TLS ingress configuration with cert-manager
    - record commit sha in evidence link

- **task 4.5: implement Secret Manager basic auth integration**
  - description: create store_basic_auth_gcp(config, username, password) function that stores basic authentication credentials in Secret Manager. generate bcrypt hash of password using htpasswd, create auth string in format "username:bcrypt_hash", store in Secret Manager secret named "{cluster_name}-basic-auth", grant secretAccessor role to workload SA, verify secret created and accessible, return boolean success status. implement credential validation (password complexity, username format).
  - acceptance criteria:
    1. function validates username format (alphanumeric, no spaces)
    2. function validates password complexity (min 8 chars)
    3. bcrypt hash generated using htpasswd -nbB {username} {password}
    4. Secret Manager secret created with name pattern {cluster}-basic-auth
    5. secret version added with auth string value
    6. IAM binding grants roles/secretmanager.secretAccessor to workload SA
    7. secret retrievable by workload identity test
    8. function returns True on successful storage
  - test scenario(s):
    - **scenario: store basic auth credentials**
      - steps: call function with valid username/password → verify secret created → test retrieval
      - expected result: secret exists in Secret Manager, value is bcrypt hash, retrieval succeeds
      - evidence: [placeholder for gcloud secrets list output]
    - **scenario: validate credentials**
      - steps: call function with weak password → observe validation error
      - expected result: error message displayed, secret not created
      - evidence: [placeholder for validation error]
  - owner: backend engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase4:4.5): implement Secret Manager basic auth storage
    - record commit sha in evidence link

- **task 4.6: implement configure_basic_auth_gcp function**
  - description: create configure_basic_auth_gcp(config, namespace) function that configures basic authentication for n8n ingress using credentials from Secret Manager. prompt user for username and password, store credentials in Secret Manager via store_basic_auth_gcp, create Kubernetes secret "basic-auth" in ingress-nginx namespace from Secret Manager value, patch ingress with annotations (nginx.ingress.kubernetes.io/auth-type: basic, nginx.ingress.kubernetes.io/auth-secret: basic-auth, nginx.ingress.kubernetes.io/auth-realm: "n8n authentication"), verify basic auth works by testing HTTP request, return boolean success status.
  - acceptance criteria:
    1. function prompts user for username and password interactively
    2. credentials stored in Secret Manager via store_basic_auth_gcp
    3. Kubernetes secret "basic-auth" created in ingress-nginx namespace
    4. secret contains auth file in htpasswd format
    5. ingress patched with 3 basic auth annotations
    6. HTTP request to ingress without credentials returns 401 Unauthorized
    7. HTTP request with correct credentials returns 200 OK
    8. function returns True when auth configured successfully
  - test scenario(s):
    - **scenario: configure basic auth**
      - steps: call function → provide credentials → verify ingress patched → test access
      - expected result: unauthenticated access denied, authenticated access granted
      - evidence: [placeholder for curl outputs with and without auth]
    - **scenario: disable basic auth**
      - steps: configure auth → remove auth annotations → verify open access
      - expected result: ingress accessible without credentials after removal
      - evidence: [placeholder for ingress after auth removal]
  - owner: backend engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase4:4.6): implement basic auth configuration for GCP
    - record commit sha in evidence link

- **task 4.7: integrate TLS and basic auth into GCP deployment flow**
  - description: update main function GCP deployment flow to include Phase 4 (TLS and basic auth configuration) after LoadBalancer URL retrieval. implement conditional execution based on loadbalancer_url availability, call configure_tls_gcp if TLS enabled in config, call configure_basic_auth_gcp if basic auth enabled, display HTTPS URL and access instructions, update completion message with security status (TLS enabled, basic auth enabled). implement --configure-tls flag support for GCP to configure TLS on existing deployments.
  - acceptance criteria:
    1. Phase 4 executes after successful Phase 3 (LoadBalancer URL retrieval)
    2. TLS configuration called if config.enable_tls == True
    3. basic auth configuration called if config.enable_basic_auth == True
    4. HTTPS URL displayed if TLS enabled (https://{domain})
    5. completion message includes security status indicators
    6. --configure-tls flag works with --cloud-provider gcp
    7. TLS configuration retrieves existing config from terraform.tfvars
    8. Phase 4 skipped if LoadBalancer URL not available
  - test scenario(s):
    - **scenario: deploy with TLS and basic auth**
      - steps: configure deployment with both enabled → complete phases 1-4 → verify security
      - expected result: HTTPS works, basic auth prompts, completion message shows both enabled
      - evidence: [placeholder for secured deployment screenshot]
    - **scenario: configure TLS on existing deployment**
      - steps: deploy without TLS → run --configure-tls → verify TLS added
      - expected result: certificate issued, ingress updated to HTTPS
      - evidence: [placeholder for TLS configuration on existing cluster]
  - owner: backend engineer
  - estimate: 4 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase4:4.7): integrate TLS and basic auth into GCP deployment
    - record commit sha in evidence link

- **task 4.8: implement --restore-region support for GCP**
  - description: update main function --restore-region handling to support GCP cloud provider. implement GCP-specific state restoration from terraform/gcp/terraform.tfstate.{region}.backup files, verify state file exists before restoration, copy backup to terraform.tfstate, display restored configuration (project, region, cluster), support --restore-region with --teardown for selective region cleanup, implement state validation after restoration.
  - acceptance criteria:
    1. --restore-region flag works with --cloud-provider gcp
    2. state file path uses terraform/gcp directory
    3. backup file naming: terraform.tfstate.{region}.backup
    4. state validation verifies resources match region
    5. restored configuration displayed to user
    6. --restore-region us-central1 --teardown combination works
    7. error handling for missing backup files
    8. success message includes restored region and cluster info
  - test scenario(s):
    - **scenario: restore us-central1 state**
      - steps: deploy to us-central1 and us-east1 → run --restore-region us-central1 → verify state
      - expected result: terraform.tfstate matches us-central1 deployment
      - evidence: [placeholder for state restoration output]
    - **scenario: restore and teardown specific region**
      - steps: run --restore-region us-east1 --teardown → verify only us-east1 deleted
      - expected result: us-east1 resources removed, us-central1 untouched
      - evidence: [placeholder for selective teardown verification]
  - owner: backend engineer
  - estimate: 3 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: feat(phase4:4.8): implement restore-region support for GCP
    - record commit sha in evidence link

- **task 4.9: update documentation for GCP**
  - description: update README.md to include GCP in supported providers list with example command. update docs/getting-started.md to add GCP deployment instructions section (parallel to AWS/Azure). update docs/guides/gcp-requirements.md to add deployment walkthrough section covering all 4 phases, screenshots, troubleshooting common issues, cost breakdown, and production deployment checklist. create docs/deployment/gcp.md mirroring aws.md and azure.md structure with comprehensive deployment guide. update docs/reference/requirements.md to include gcloud CLI in tools list.
  - acceptance criteria:
    1. README.md lists GCP as third supported provider
    2. README.md includes `python3 setup.py --cloud-provider gcp` example
    3. docs/getting-started.md has GCP deployment section
    4. docs/guides/gcp-requirements.md contains deployment walkthrough with phases
    5. docs/deployment/gcp.md created with 1000+ lines (matching AWS/Azure depth)
    6. docs/reference/requirements.md updated with gcloud CLI requirement
    7. all GCP documentation includes cost estimates
    8. troubleshooting section covers 10+ common issues
    9. screenshots/diagrams included where helpful
    10. documentation reviewed for accuracy and completeness
  - test scenario(s):
    - **scenario: follow GCP deployment guide as new user**
      - steps: new user reads docs/deployment/gcp.md → follows steps → deploys successfully
      - expected result: deployment succeeds following only documentation
      - evidence: [placeholder for user test feedback]
    - **scenario: troubleshooting guide validation**
      - steps: introduce common errors → consult troubleshooting section → resolve issues
      - expected result: troubleshooting steps resolve issues effectively
      - evidence: [placeholder for resolved issue examples]
  - owner: technical writer + backend engineer
  - estimate: 10 h
  - status: [ ] todo
  - evidence link: [placeholder for commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: docs(phase4:4.9): comprehensive GCP documentation updates
    - record commit sha in evidence link

- **task 4.10: production deployment validation**
  - description: execute production-grade deployment in real GCP production project (not test project) to validate complete implementation. deploy GKE cluster with Cloud SQL PostgreSQL in production region, configure custom domain with real DNS records, enable TLS with Let's Encrypt production certificates, configure basic authentication, create test n8n workflows and verify persistence, test workflow execution end-to-end, verify monitoring and logging, measure actual costs over 7 days, document production deployment experience, identify any gaps or issues, create production readiness checklist.
  - acceptance criteria:
    1. production deployment in real GCP project succeeds
    2. Cloud SQL PostgreSQL used for database
    3. real domain configured with valid DNS records
    4. Let's Encrypt production certificate issued successfully
    5. basic authentication functional
    6. n8n workflows created and persist across pod restarts
    7. workflow execution succeeds (HTTP request, data transformation, etc.)
    8. Cloud Operations logging captures n8n logs
    9. actual costs measured and documented
    10. production readiness checklist created and verified
  - test scenario(s):
    - **scenario: production deployment end-to-end**
      - steps: production project → deploy with Cloud SQL → configure domain → enable TLS → enable auth → create workflows → monitor for 7 days
      - expected result: deployment stable, workflows execute reliably, costs within estimates
      - evidence: [placeholder for production deployment report]
    - **scenario: workflow persistence test**
      - steps: create workflow → save → delete n8n pod → verify workflow still exists
      - expected result: workflow data persists in Cloud SQL, survives pod deletion
      - evidence: [placeholder for persistence test]
    - **scenario: cost validation**
      - steps: monitor GCP billing for 7 days → calculate monthly projection → compare to estimates
      - expected result: actual costs within 10% of estimated $212/month for Cloud SQL config
      - evidence: [placeholder for billing screenshots]
  - owner: senior engineer + product manager
  - estimate: 12 h
  - status: [ ] todo
  - evidence link: [placeholder for production validation report and commit SHA]
  - git actions (end of task):
    - commit: yes
    - suggested message: test(phase4:4.10): production deployment validation and readiness
    - record commit sha in evidence link

### risks and mitigations

- **risk: Let's Encrypt rate limits prevent production certificate issuance** → **mitigation:** implement staging mode first; document rate limits (50 certs per domain per week); provide manual certificate instructions
- **risk: DNS propagation delays cause certificate validation failures** → **mitigation:** implement 5-10 minute wait after DNS configuration prompt; verify DNS resolution before cert request; provide manual retry option
- **risk: basic auth credentials exposed in logs or terraform state** → **mitigation:** use sensitive=true for all credential outputs; implement credential rotation documentation; audit logs for credential leaks
- **risk: teardown failures leave orphaned resources incurring costs** → **mitigation:** implement comprehensive resource listing before teardown; provide manual cleanup instructions; implement cost monitoring alerts
- **risk: production deployment issues not caught in testing** → **mitigation:** use real production project for validation; involve external tester; create production deployment checklist
- **risk: documentation becomes outdated quickly** → **mitigation:** version documentation with code; implement doc review as part of testing; create documentation maintenance plan

### dependencies

- phase 3 completed (deployment automation functional)
- cert-manager helm chart available (jetstack repository)
- Let's Encrypt production API accessible
- test domain available for TLS testing
- production GCP project for final validation
- htpasswd tool installed for basic auth hashing

### completion checklist (exit criteria)

- [ ] all phase-level acceptance criteria met
- [ ] all task test scenarios passed
- [ ] uat executed and recorded
- [ ] documentation updated (links)
- [ ] phase commit created and pushed (sha recorded)
- [ ] teardown tested and verified across 3 scenarios
- [ ] TLS configuration tested with Let's Encrypt
- [ ] basic authentication tested and functional
- [ ] production deployment completed successfully
- [ ] cost validation completed (7-day monitoring)
- [ ] all documentation reviewed and approved
- [ ] production readiness checklist verified
- [ ] external user testing completed successfully

### git actions (end of phase)

- create a commit summarizing the phase completion
- push to the remote repository
- record branch and commit sha

### phase execution report

*(fill after execution)*

- **what was done:**
  - tasks completed with links and evidence

- **test results summary:**
  - scenarios run: 0
  - pass: 0
  - fail: 0
  - defects found: 0 (links)

- **challenges encountered:**
  - description and how each was handled

- **learnings:**
  - key takeaways and recommendations

- **decision:**
  - go/no-go and rationale

- **git evidence:**
  - task commits: list shas
  - phase commit and push: branch and sha

- **next phase readiness:**
  - entry criteria confirmed (n/a - final phase)

---

## traceability mapping

### acceptance criteria traceability

- **AC: GCPDeploymentConfig class instantiates successfully with all 18 required attributes**
  - linked tasks: 1.1, 1.5
  - linked uat scenarios: complete GCP configuration collection with valid inputs

- **AC: GCPAuthChecker.verify_credentials returns (True, "authenticated as ...") for valid gcloud credentials**
  - linked tasks: 1.2
  - linked uat scenarios: detect invalid GCP credentials

- **AC: terraform apply creates GKE cluster accessible via kubectl in under 25 minutes**
  - linked tasks: 2.4, 2.7, 2.9
  - linked uat scenarios: deploy GKE cluster with SQLite, deploy GKE cluster with Cloud SQL PostgreSQL

- **AC: `python3 setup.py --cloud-provider gcp` completes full deployment successfully**
  - linked tasks: 3.1, 3.4, 3.6, 3.9
  - linked uat scenarios: complete GCP deployment with SQLite, complete GCP deployment with Cloud SQL

- **AC: n8n UI accessible via LoadBalancer URL (HTTP, port 80)**
  - linked tasks: 3.8, 3.9
  - linked uat scenarios: LoadBalancer URL retrieval

- **AC: workload identity binding allows pod to read Secret Manager encryption key**
  - linked tasks: 3.3, 3.9
  - linked uat scenarios: verify workload identity in deployed pod

- **AC: GKETeardown.execute() completes 4-phase teardown successfully**
  - linked tasks: 4.1
  - linked uat scenarios: complete teardown of GCP deployment

- **AC: Let's Encrypt certificate issued successfully and bound to ingress**
  - linked tasks: 4.2, 4.3, 4.4, 4.7
  - linked uat scenarios: configure TLS with Let's Encrypt

- **AC: basic authentication configured with credentials stored in Secret Manager**
  - linked tasks: 4.5, 4.6, 4.7
  - linked uat scenarios: configure basic authentication

- **AC: production deployment succeeds in real GCP environment**
  - linked tasks: 4.10
  - linked uat scenarios: production deployment end-to-end

---

*end of plan*
