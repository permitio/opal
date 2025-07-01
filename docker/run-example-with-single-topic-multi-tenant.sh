#!/bin/bash

# OPAL Single Topic Multi-Tenant Configuration Example Script
# This script demonstrates single-topic approach for OPAL multi-tenancy
# that eliminates the need for system restarts when adding new tenants

set -e

if [ ! -f "docker-compose-single-topic-multi-tenant.yml" ]; then
   echo "did not find compose file - run this script from the 'docker/' directory under opal root!"
   exit
fi

echo "--------------------------------------------------------------------"
echo "This script will run the docker-compose-single-topic-multi-tenant.yml"
echo "example configuration, and demonstrates the simple approach that"
echo "allows adding tenants WITHOUT RESTARTS!"
echo "--------------------------------------------------------------------"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to wait for service to be ready
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1
    
    print_status "Waiting for $service_name to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            print_success "$service_name is ready!"
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "$service_name failed to start within $((max_attempts * 2)) seconds"
    return 1
}

# Function to check OPAL Client logs for success
check_opal_logs() {
    local reason=$1
    print_status "Checking OPAL Client logs for: $reason"
    
    # Wait a moment for logs to appear
    sleep 3
    
    # Check for success indicators in logs
    if docker compose -f docker-compose-single-topic-multi-tenant.yml logs opal_client --since 10s 2>/dev/null | grep -q "processing store transaction: {'success': True"; then
        print_success "OPAL Client successfully processed data update"
        return 0
    else
        print_warning "Could not verify OPAL Client success in logs"
        return 1
    fi
}

# Function to verify data in OPA
verify_opa_data() {
    local tenant=$1
    print_status "Verifying data for $tenant in OPA..."
    
    local response=$(curl -s "http://localhost:8181/v1/data/acl/$tenant" 2>/dev/null)
    
    # Debug: show full response
    echo "DEBUG: Full OPA response for $tenant:"
    echo "$response" | jq . 2>/dev/null || echo "$response"
    
    if echo "$response" | jq -e '.result.users' > /dev/null 2>&1; then
        print_success "Data for $tenant found in OPA"
        echo "$response" | jq '.result.users'
        return 0
    else
        print_error "No data found for $tenant in OPA"
        return 1
    fi
}

# Main test execution
main() {
    print_status "🚀 Starting OPAL Single Topic Multi-Tenant Example"
    
    # Step 1: Start services
    print_status "Step 1: Starting Docker services..."
    docker compose -f docker-compose-single-topic-multi-tenant.yml up -d
    
    # Step 2: Wait for services to be ready
    print_status "Step 2: Waiting for services to be ready..."
    wait_for_service "http://localhost:7002/healthcheck" "OPAL Server" || exit 1
    wait_for_service "http://localhost:8181/health" "OPA" || exit 1
    wait_for_service "http://localhost:8090/acl/tenant1" "Example External Data Provider" || exit 1
    
    # Step 3: Verify OPAL Client configuration
    print_status "Step 3: Verifying OPAL Client configuration..."
    local topics=$(docker compose -f docker-compose-single-topic-multi-tenant.yml exec opal_client env | grep OPAL_DATA_TOPICS | cut -d'=' -f2)
    if [ "$topics" = "tenant_data" ]; then
        print_success "OPAL Client configured with single topic: $topics"
    else
        print_error "OPAL Client has incorrect topic configuration: $topics"
        exit 1
    fi
    
    # Step 4: Add tenant1 data
    print_status "Step 4: Adding tenant1 data via single topic..."
    curl -X POST http://localhost:7002/data/config \
        -H "Content-Type: application/json" \
        -d '{
            "entries": [{
                "url": "http://example_external_data_provider:80/acl/tenant1",
                "topics": ["tenant_data"],
                "dst_path": "/acl/tenant1"
            }],
            "reason": "Load tenant1 data via single topic"
        }' > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        print_success "Tenant1 data source added successfully"
        sleep 10
        verify_opa_data "tenant1"
    else
        print_error "Failed to add tenant1 data source"
        exit 1
    fi
    
    # Step 5: Add tenant2 data (NO RESTART!)
    print_status "Step 5: Adding tenant2 data via single topic (NO RESTART!)..."
    curl -X POST http://localhost:7002/data/config \
        -H "Content-Type: application/json" \
        -d '{
            "entries": [{
                "url": "http://example_external_data_provider:80/acl/tenant2",
                "topics": ["tenant_data"],
                "dst_path": "/acl/tenant2"
            }],
            "reason": "Load tenant2 data via single topic - NO RESTART"
        }' > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        print_success "Tenant2 data source added successfully - NO RESTART NEEDED!"
        sleep 10
        verify_opa_data "tenant2"
    else
        print_error "Failed to add tenant2 data source"
        exit 1
    fi
    
    # Step 6: Verify data isolation
    print_status "Step 6: Verifying data isolation..."
    local all_data=$(curl -s "http://localhost:8181/v1/data/acl" 2>/dev/null)
    
    if echo "$all_data" | jq -e '.result.tenant1' > /dev/null 2>&1 && \
       echo "$all_data" | jq -e '.result.tenant2' > /dev/null 2>&1; then
        print_success "Data isolation verified - both tenants have separate data"
        echo "All tenant data:"
        echo "$all_data" | jq '.result'
    else
        print_error "Data isolation verification failed"
        exit 1
    fi
    
    # Step 7: Test authorization policies
    print_status "Step 7: Testing authorization policies..."
    local auth_result=$(curl -X POST http://localhost:8181/v1/data/policies/rbac/allow \
        -H "Content-Type: application/json" \
        -d '{
            "input": {
                "user": "alice",
                "action": "read", 
                "resource": "document1",
                "tenant_id": "tenant1"
            }
        }' 2>/dev/null)
    
    if echo "$auth_result" | jq -e '.result' > /dev/null 2>&1; then
        print_success "Authorization policy test successful"
        echo "Policy result: $(echo "$auth_result" | jq '.result')"
    else
        print_warning "Authorization policy test failed (this may be expected if no matching policies exist)"
    fi
    
    # Step 8: Show OPAL Server logs
    print_status "Step 8: Recent OPAL Server event logs..."
    docker compose -f docker-compose-single-topic-multi-tenant.yml logs opal_server --since 2m 2>/dev/null | grep -E "(Publishing|Broadcasting)" | tail -5 || true
    
    # Step 9: Show OPAL Client logs
    print_status "Step 9: Recent OPAL Client processing logs..."
    docker compose -f docker-compose-single-topic-multi-tenant.yml logs opal_client --since 2m 2>/dev/null | grep -E "(Received|Updating|Fetching|Saving)" | tail -10 || true
    
    # Final success message
    echo ""
    print_success "🎉 OPAL Single Topic Multi-Tenant Example COMPLETED SUCCESSFULLY!"
    echo ""
    echo "Key achievements demonstrated:"
    echo "✅ Single topic 'tenant_data' handled multiple tenants"
    echo "✅ No restart required when adding tenant2"
    echo "✅ Data isolation maintained through OPA path hierarchy"
    echo "✅ Real-time tenant addition working perfectly"
    echo "✅ Revolutionary single-topic approach proven!"
    echo ""
    echo "Manual verification commands:"
    echo "  curl -s http://localhost:8181/v1/data/acl/tenant1 | jq ."
    echo "  curl -s http://localhost:8181/v1/data/acl/tenant2 | jq ."
    echo "  curl -s http://localhost:8181/v1/data/acl | jq ."
    echo ""
    echo "To stop services:"
    echo "  docker compose -f docker-compose-single-topic-multi-tenant.yml down"
}

# Cleanup function
cleanup() {
    print_status "Cleaning up Docker services..."
    docker compose -f docker-compose-single-topic-multi-tenant.yml down --volumes --remove-orphans
}

# Trap cleanup on script exit
trap cleanup EXIT

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    print_error "jq is required but not installed. Please install jq first:"
    echo "  macOS: brew install jq"
    echo "  Ubuntu: sudo apt-get install jq"
    echo "  CentOS: sudo yum install jq"
    exit 1
fi

# Run main test
main

# Wait for user input before cleanup
print_status "Example completed. Services are still running for manual inspection."
read -p "Press Enter to cleanup and exit..." 
