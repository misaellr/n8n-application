#!/bin/bash
# GCP Leftover Resources Check Script
# Checks for any remaining n8n-related resources after teardown

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
PROJECT_ID="${GCP_PROJECT_ID:-}"
CLUSTER_NAME="${CLUSTER_NAME:-n8n-gke-cluster}"
VPC_NAME="${VPC_NAME:-n8n-vpc}"

# Function to print section header
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Function to check resource existence
check_resource() {
    local resource_type=$1
    local count=$2

    if [ "$count" -eq 0 ]; then
        echo -e "${GREEN}✓ No leftover $resource_type${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠  Found $count leftover $resource_type${NC}"
        return 1
    fi
}

# Get project ID if not provided
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}No PROJECT_ID provided. Trying to detect from gcloud config...${NC}"
    PROJECT_ID=$(gcloud config get-value project 2>/dev/null)

    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}Error: Could not determine GCP project ID${NC}"
        echo "Please set GCP_PROJECT_ID environment variable or configure gcloud project"
        exit 1
    fi
fi

echo -e "${BLUE}Checking GCP resources for project: ${PROJECT_ID}${NC}"
echo -e "${BLUE}Cluster pattern: ${CLUSTER_NAME}*${NC}"
echo -e "${BLUE}VPC pattern: ${VPC_NAME}*${NC}\n"

# Track if any resources found
RESOURCES_FOUND=0

# Check GKE Clusters
print_header "1. GKE Clusters"
CLUSTERS=$(gcloud container clusters list --project="$PROJECT_ID" --format="value(name)" 2>/dev/null | grep -i "n8n\|$CLUSTER_NAME" || true)
COUNT=$(echo "$CLUSTERS" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$CLUSTERS"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    for cluster in $CLUSTERS; do
        LOCATION=$(gcloud container clusters list --project="$PROJECT_ID" --filter="name=$cluster" --format="value(location)")
        echo "  gcloud container clusters delete $cluster --location=$LOCATION --project=$PROJECT_ID --quiet"
    done
    RESOURCES_FOUND=1
fi
check_resource "GKE clusters" "$COUNT"

# Check Cloud SQL Instances
print_header "2. Cloud SQL Instances"
SQL_INSTANCES=$(gcloud sql instances list --project="$PROJECT_ID" --format="value(name)" 2>/dev/null | grep -i "n8n\|postgres" || true)
COUNT=$(echo "$SQL_INSTANCES" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$SQL_INSTANCES"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    for instance in $SQL_INSTANCES; do
        echo "  gcloud sql instances delete $instance --project=$PROJECT_ID --quiet"
    done
    RESOURCES_FOUND=1
fi
check_resource "Cloud SQL instances" "$COUNT"

# Check VPC Networks
print_header "3. VPC Networks"
VPCS=$(gcloud compute networks list --project="$PROJECT_ID" --format="value(name)" 2>/dev/null | grep -i "$VPC_NAME" || true)
COUNT=$(echo "$VPCS" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$VPCS"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    for vpc in $VPCS; do
        echo "  gcloud compute networks delete $vpc --project=$PROJECT_ID --quiet"
    done
    RESOURCES_FOUND=1
fi
check_resource "VPC networks" "$COUNT"

# Check Subnets
print_header "4. Subnets"
SUBNETS=$(gcloud compute networks subnets list --project="$PROJECT_ID" --format="value(name,region)" 2>/dev/null | grep -i "n8n" || true)
COUNT=$(echo "$SUBNETS" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$SUBNETS"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    while IFS=$'\t' read -r subnet region; do
        [ -z "$subnet" ] && continue
        echo "  gcloud compute networks subnets delete $subnet --region=$region --project=$PROJECT_ID --quiet"
    done <<< "$SUBNETS"
    RESOURCES_FOUND=1
fi
check_resource "subnets" "$COUNT"

# Check Global Addresses
print_header "5. Global IP Addresses"
ADDRESSES=$(gcloud compute addresses list --global --project="$PROJECT_ID" --format="value(name)" 2>/dev/null | grep -i "n8n" || true)
COUNT=$(echo "$ADDRESSES" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$ADDRESSES"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    for addr in $ADDRESSES; do
        echo "  gcloud compute addresses delete $addr --global --project=$PROJECT_ID --quiet"
    done
    RESOURCES_FOUND=1
fi
check_resource "global addresses" "$COUNT"

# Check Regional Addresses
print_header "6. Regional IP Addresses"
ADDRESSES=$(gcloud compute addresses list --project="$PROJECT_ID" --format="value(name,region)" 2>/dev/null | grep -i "n8n" || true)
COUNT=$(echo "$ADDRESSES" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$ADDRESSES"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    while IFS=$'\t' read -r addr region; do
        [ -z "$addr" ] && continue
        echo "  gcloud compute addresses delete $addr --region=$region --project=$PROJECT_ID --quiet"
    done <<< "$ADDRESSES"
    RESOURCES_FOUND=1
fi
check_resource "regional addresses" "$COUNT"

# Check Service Accounts
print_header "7. Service Accounts"
SAS=$(gcloud iam service-accounts list --project="$PROJECT_ID" --format="value(email)" 2>/dev/null | grep -i "n8n\|$CLUSTER_NAME" || true)
COUNT=$(echo "$SAS" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$SAS"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    for sa in $SAS; do
        echo "  gcloud iam service-accounts delete $sa --project=$PROJECT_ID --quiet"
    done
    RESOURCES_FOUND=1
fi
check_resource "service accounts" "$COUNT"

# Check Secret Manager Secrets
print_header "8. Secret Manager Secrets"
SECRETS=$(gcloud secrets list --project="$PROJECT_ID" --format="value(name)" 2>/dev/null | grep -i "n8n" || true)
COUNT=$(echo "$SECRETS" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$SECRETS"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    for secret in $SECRETS; do
        echo "  gcloud secrets delete $secret --project=$PROJECT_ID --quiet"
    done
    RESOURCES_FOUND=1
fi
check_resource "secrets" "$COUNT"

# Check Compute Routers
print_header "9. Compute Routers"
ROUTERS=$(gcloud compute routers list --project="$PROJECT_ID" --format="value(name,region)" 2>/dev/null | grep -i "n8n" || true)
COUNT=$(echo "$ROUTERS" | grep -v "^$" | wc -l)
if [ "$COUNT" -gt 0 ]; then
    echo "$ROUTERS"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    while IFS=$'\t' read -r router region; do
        [ -z "$router" ] && continue
        echo "  gcloud compute routers delete $router --region=$region --project=$PROJECT_ID --quiet"
    done <<< "$ROUTERS"
    RESOURCES_FOUND=1
fi
check_resource "compute routers" "$COUNT"

# Check Service Networking Connections
print_header "10. Service Networking Connections"
echo -e "${BLUE}Checking VPC peering connections...${NC}"
PEERINGS=$(gcloud services vpc-peerings list --network="$VPC_NAME" --project="$PROJECT_ID" 2>/dev/null || true)
if [ -n "$PEERINGS" ] && [ "$PEERINGS" != "Listed 0 items." ]; then
    echo "$PEERINGS"
    echo -e "${YELLOW}Manual cleanup:${NC}"
    echo "  gcloud services vpc-peerings delete --service=servicenetworking.googleapis.com --network=$VPC_NAME --project=$PROJECT_ID --quiet"
    RESOURCES_FOUND=1
    check_resource "service networking connections" 1
else
    check_resource "service networking connections" 0
fi

# Final Summary
print_header "Summary"
if [ $RESOURCES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✅ No leftover n8n resources found in project $PROJECT_ID${NC}"
    echo -e "${GREEN}Teardown completed successfully!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some n8n resources still exist in project $PROJECT_ID${NC}"
    echo -e "${YELLOW}Review the cleanup commands above and run them manually if needed${NC}"
    echo ""
    echo -e "${BLUE}Quick cleanup script:${NC}"
    echo "# Save all commands to a file and execute:"
    echo "bash $0 | grep '  gcloud' > /tmp/gcp-cleanup.sh"
    echo "bash /tmp/gcp-cleanup.sh"
    exit 1
fi
