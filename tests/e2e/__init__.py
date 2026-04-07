"""
OPAL End-to-End Testing Framework

This package provides a comprehensive PyTest-based E2E testing framework for OPAL.
It replaces the bash-based testing approach with a more maintainable and extensible
Python solution.

Key Features:
- Automated setup and teardown of test environment
- Docker-based testing with Gitea, OPAL server, and OPAL client
- Comprehensive test coverage for health, connectivity, policy updates, and data updates
- Resilience testing for broadcast channel failures
- Statistics and monitoring verification

Usage:
    pytest tests/e2e/

For more information, see tests/e2e/README.md
"""

__version__ = "1.0.0"
