#!/bin/bash

# Quick Reference - Running Tests for Generated Policies
# Usage: Source this file or run individual commands

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       OPAL Test Policies - Quick Start Guide               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Show what was generated
echo -e "${GREEN}✅ Generated Assets:${NC}"
echo "   • 1000 Rego policies (policies/policy_*.rego)"
echo "   • 100 JSON data files (test_data/testdata_*.json)"
echo "   • Comprehensive test suite (policy_tests/test_policies.py)"
echo ""

# Show test options
echo -e "${BLUE}📝 Test Options:${NC}"
echo ""
echo -e "${YELLOW}Option 1: Basic Tests (No OPA Required)${NC}"
echo "   python3 -m pytest policy_tests/test_policies.py -v"
echo "   ✓ Checks file counts"
echo "   ✓ Validates package names (4+ levels)"
echo "   ✓ Verifies JSON format"
echo ""

echo -e "${YELLOW}Option 2: Full Tests (Requires OPA)${NC}"
echo "   ./run_tests.sh"
echo "   ✓ Runs all tests above"
echo "   ✓ Validates Rego syntax"
echo "   ✓ Tests policy compilation"
echo "   ✓ Evaluates policies against test data"
echo ""

echo -e "${YELLOW}Option 3: Specific Test Class${NC}"
echo "   python3 -m pytest policy_tests/test_policies.py::TestREGOPolicies -v"
echo "   python3 -m pytest policy_tests/test_policies.py::TestDataQuality -v"
echo ""

# Show OPA commands
echo -e "${BLUE}🔧 OPA Direct Commands:${NC}"
echo ""
echo "Check policy syntax:"
echo "  opa check policies/policy_0001.rego"
echo ""
echo "Build all policies:"
echo "  opa build -b policies/"
echo ""
echo "Evaluate policy:"
echo "  opa eval -d policies/policy_0001.rego -i test_data/testdata_001.json 'data'"
echo ""

# Show file structure
echo -e "${BLUE}📁 File Structure:${NC}"
echo "   policies/              - 1000 Rego policies"
echo "   test_data/             - 100 JSON test datasets"
echo "   policy_tests/          - pytest test suite"
echo "   generate_policies.py   - Regeneration script"
echo "   GENERATION_SUMMARY.md  - Detailed documentation"
echo "   GENERATED_README.md    - Full README"
echo ""

# Show package hierarchy info
echo -e "${BLUE}📦 Package Hierarchy Example:${NC}"
echo "   package domain.module.component.rule_type[.suffix].policy_id"
echo ""
echo "   Examples:"
echo "   • security.authorization.user.allow.core.policy_0001"
echo "   • compliance.validation.resource.deny.utils.policy_0500"
echo "   • access.enforcement.action.check.helpers.policy_0999"
echo ""

# Quick command examples
echo -e "${BLUE}⚡ Quick Commands:${NC}"
echo ""
echo "cd test-policies"
echo "python3 -m pytest policy_tests/test_policies.py -v"
echo ""

echo -e "${GREEN}✨ Ready to test! Choose an option above.${NC}"
