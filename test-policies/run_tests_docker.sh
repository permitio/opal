#!/bin/bash
# Docker-based test runner for OPAL policies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
DOCKER_IMAGE_NAME="opal-policy-tests"
DOCKER_CONTAINER_NAME="opal-policy-tests-runner"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        OPAL Test Policies - Docker Test Runner             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed or not in PATH${NC}"
    echo "   Install Docker from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

echo -e "${GREEN}✓ Docker found${NC}"
DOCKER_VERSION=$(docker --version)
echo "  $DOCKER_VERSION"
echo ""

# Create results directory
mkdir -p "$RESULTS_DIR"
echo -e "${GREEN}✓ Results directory: $RESULTS_DIR${NC}"
echo ""

# Check if we should rebuild the image
REBUILD_FLAG="${1:-}"
if [ "$REBUILD_FLAG" = "--rebuild" ]; then
    echo -e "${YELLOW}Removing existing image for rebuild...${NC}"
    docker rmi "$DOCKER_IMAGE_NAME" 2>/dev/null || true
fi

# Build Docker image
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Building Docker image: $DOCKER_IMAGE_NAME${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if docker build -t "$DOCKER_IMAGE_NAME" -f "$SCRIPT_DIR/Dockerfile.opa-test" "$SCRIPT_DIR" 2>&1 | tail -20; then
    echo -e "${GREEN}✓ Docker image built successfully${NC}"
else
    echo -e "${RED}✗ Failed to build Docker image${NC}"
    exit 1
fi
echo ""

# Run tests in Docker container
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Running tests in Docker container${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Remove old container if exists
docker rm "$DOCKER_CONTAINER_NAME" 2>/dev/null || true

# Run the container
if docker run --rm \
    --name "$DOCKER_CONTAINER_NAME" \
    -v "$SCRIPT_DIR/policies:/app/policies:rw" \
    -v "$SCRIPT_DIR/test_data:/app/test_data:ro" \
    -v "$SCRIPT_DIR/policy_tests:/app/policy_tests:ro" \
    -v "$RESULTS_DIR:/app/results:rw" \
    "$DOCKER_IMAGE_NAME"; then
    TEST_EXIT_CODE=$?
else
    TEST_EXIT_CODE=$?
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test Execution Complete${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Display results
if [ -f "$RESULTS_DIR/test_report.txt" ]; then
    echo -e "${GREEN}✓ Test report generated${NC}"
    echo ""
    echo "Full report:"
    echo "  📄 $RESULTS_DIR/test_report.txt"
    echo ""
    
    if [ -f "$RESULTS_DIR/policies.wasm" ]; then
        WASM_SIZE=$(du -sh "$RESULTS_DIR/policies.wasm" | cut -f1)
        echo "Generated artifacts:"
        echo "  📦 $RESULTS_DIR/policies.wasm ($WASM_SIZE)"
        echo ""
    fi
else
    echo -e "${RED}✗ Test report not found${NC}"
fi

# Show summary
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              ✅ ALL DOCKER TESTS PASSED ✅                 ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║             ❌ SOME DOCKER TESTS FAILED ❌                 ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
fi

echo ""

# Exit with test result code
exit $TEST_EXIT_CODE
