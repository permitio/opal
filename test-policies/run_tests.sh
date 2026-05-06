#!/bin/bash
# Test runner script for OPAL test policies

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICIES_DIR="$SCRIPT_DIR/policies"
TEST_DATA_DIR="$SCRIPT_DIR/test_data"
TESTS_DIR="$SCRIPT_DIR/policy_tests"

echo "========================================"
echo "OPAL Test Policies - Local Test Runner"
echo "========================================"
echo ""

# Check if OPA is installed (try multiple locations)
OPA_CMD=""
if command -v opa &> /dev/null; then
    OPA_CMD="opa"
elif [ -f "/opt/homebrew/bin/opa" ]; then
    OPA_CMD="/opt/homebrew/bin/opa"
elif [ -f "/opt/homebrew/Cellar/opa/*/bin/opa" ]; then
    OPA_CMD=$(find /opt/homebrew/Cellar/opa -name "opa" -type f 2>/dev/null | head -1)
fi

# Check if OPA is available
if [ -z "$OPA_CMD" ]; then
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
if [ ! -z "$OPA_CMD" ]; then
    echo "✓ Running OPA syntax checks..."
    for policy in "$POLICIES_DIR"/*.rego; do
        if ! $OPA_CMD check "$policy" > /dev/null 2>&1; then
            echo "✗ Syntax error in $(basename "$policy")"
            exit 1
        fi
    done
    echo "✓ All policies have valid Rego syntax"
    echo ""
fi

# Run pytest if available
if python3 -m pytest --version &> /dev/null; then
    echo "✓ Running pytest test suite..."
    cd "$TESTS_DIR"
    python3 -m pytest test_policies.py -v --tb=short
else
    echo "⚠️  pytest not found. Install with: python3 -m pip install pytest"
    echo "   Then run: python3 -m pytest policy_tests/test_policies.py -v"
fi

echo ""
echo "✓ Test run complete!"
