#!/bin/bash
# Test runner script for OPAL test policies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICIES_DIR="$SCRIPT_DIR/policies"
TEST_DATA_DIR="$SCRIPT_DIR/test_data"
TESTS_DIR="$SCRIPT_DIR/policy_tests"

echo "========================================"
echo "OPAL Test Policies - Local Test Runner"
echo "========================================"
echo ""

# Check if OPA is installed
if ! command -v opa &> /dev/null; then
    echo "⚠️  Warning: OPA is not installed. Some tests will be skipped."
    echo "   Install OPA from: https://www.openpolicyagent.org/docs/latest/#running-opa"
    echo ""
fi

# Count files
POLICY_COUNT=$(find "$POLICIES_DIR" -name "*.rego" | wc -l)
DATA_COUNT=$(find "$TEST_DATA_DIR" -name "*.json" | wc -l)

echo "📊 Generated Assets:"
echo "   Policies: $POLICY_COUNT"
echo "   Test Data Files: $DATA_COUNT"
echo ""

# Run syntax checks with OPA if available
if command -v opa &> /dev/null; then
    echo "✓ Running OPA syntax checks..."
    for policy in "$POLICIES_DIR"/*.rego; do
        if ! opa check "$policy" > /dev/null 2>&1; then
            echo "✗ Syntax error in $(basename "$policy")"
            exit 1
        fi
    done
    echo "✓ All policies have valid Rego syntax"
    echo ""
fi

# Run pytest if available
if command -v pytest &> /dev/null; then
    echo "✓ Running pytest test suite..."
    cd "$TESTS_DIR"
    pytest test_policies.py -v --tb=short
else
    echo "⚠️  pytest not found. Install with: pip install pytest"
    echo "   Then run: pytest policy_tests/test_policies.py -v"
fi

echo ""
echo "✓ Test run complete!"
