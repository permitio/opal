#!/bin/bash
# Simplified Docker entrypoint for OPAL policy testing
# Focus: Run comprehensive pytest suite with all tests

SCRIPT_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
RESULTS_DIR="/app/results"
REPORT_FILE="$RESULTS_DIR/test_report.txt"

mkdir -p "$RESULTS_DIR"

# Initialize report
{
  echo "╔════════════════════════════════════════════════════════════════════════════╗"
  echo "║                  OPAL TEST POLICIES - DOCKER TEST REPORT                   ║"
  echo "╚════════════════════════════════════════════════════════════════════════════╝"
  echo ""
  echo "Test Execution Start: $SCRIPT_START_TIME"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📊 ASSET INVENTORY"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  
  POLICY_COUNT=$(find /app/policies -name "*.rego" | wc -l)
  DATA_COUNT=$(find /app/test_data -name "*.json" | wc -l)
  POLICY_SIZE=$(du -sh /app/policies | cut -f1)
  DATA_SIZE=$(du -sh /app/test_data | cut -f1)
  
  echo "Total Policies: $POLICY_COUNT"
  echo "Total Test Data Files: $DATA_COUNT"
  echo "Policies Directory Size: $POLICY_SIZE"
  echo "Test Data Directory Size: $DATA_SIZE"
  echo ""
  
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "✓ OPA INFORMATION"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  
  opa version 2>&1
  echo ""
  
  # Quick OPA build test
  echo "Testing OPA compilation..."
  if opa build -b /app/policies -o "$RESULTS_DIR/policies.wasm" 2>&1; then
    echo "  ✓ Compilation successful"
    WASM_SIZE=$(du -sh "$RESULTS_DIR/policies.wasm" | cut -f1)
    echo "  Output WASM file size: $WASM_SIZE"
  else
    echo "  ✗ Compilation failed"
  fi
  echo ""
  
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "✓ RUNNING PYTEST TEST SUITE"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
} | tee -a "$REPORT_FILE"

# Run pytest with comprehensive output
cd /app/policy_tests
python3 -m pytest test_policies.py -v --tb=short 2>&1 | tee -a "$REPORT_FILE"
PYTEST_EXIT_CODE=$?

# Final summary
{
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📋 TEST SUMMARY"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Asset Inventory:"
  echo "  Policies: $POLICY_COUNT"
  echo "  Test Data Files: $DATA_COUNT"
  echo ""
  
  if [ $PYTEST_EXIT_CODE -eq 0 ]; then
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║                        ✅ ALL TESTS PASSED ✅                              ║"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
  else
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║                       ⚠️  TEST RUN COMPLETED ⚠️                             ║"
    echo "║            Check above output for test results and details                 ║"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
  fi
  
  echo ""
  SCRIPT_END_TIME=$(date '+%Y-%m-%d %H:%M:%S')
  echo "Test Execution End: $SCRIPT_END_TIME"
  echo ""
  echo "Reports generated:"
  echo "  - Text report: $REPORT_FILE"
  echo "  - WASM output: $RESULTS_DIR/policies.wasm"
  echo ""
} | tee -a "$REPORT_FILE"

# Copy report to stdout for visibility
cat "$REPORT_FILE"

# Exit with pytest exit code
exit $PYTEST_EXIT_CODE
