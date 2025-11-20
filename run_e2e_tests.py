#!/usr/bin/env python3
"""
Simple script to run E2E tests for OPAL.
This script provides an easy way to execute the E2E test suite.
"""

import subprocess
import sys
import os


def main():
    """Run the E2E test suite."""
    print("🚀 Starting OPAL E2E Tests...")
    print("=" * 50)
    
    # Change to the project directory
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    # Run pytest with E2E tests
    cmd = [
        sys.executable, "-m", "pytest", 
        "tests/e2e", 
        "-v", 
        "--tb=short",
        "-m", "e2e"
    ]
    
    try:
        result = subprocess.run(cmd, check=False)
        
        if result.returncode == 0:
            print("\n✅ All E2E tests passed!")
        else:
            print(f"\n❌ Some tests failed (exit code: {result.returncode})")
            
        return result.returncode
        
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())