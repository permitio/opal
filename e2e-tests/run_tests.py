#!/usr/bin/env python3
"""Cross-platform script to set up venv and run E2E tests."""
import os
import sys
import subprocess
import shutil
import venv

def main():
    venv_path = os.path.join(os.path.dirname(__file__), '.venv')
    
    # Determine paths based on platform
    if sys.platform == 'win32':
        python_exe = os.path.join(venv_path, 'Scripts', 'python.exe')
        activate_script = os.path.join(venv_path, 'Scripts', 'activate')
    else:
        python_exe = os.path.join(venv_path, 'bin', 'python')
        activate_script = os.path.join(venv_path, 'bin', 'activate')
    
    # Check if venv exists
    venv_exists = os.path.exists(python_exe) or os.path.exists(activate_script)
    
    # Create venv if it doesn't exist
    if not venv_exists:
        print("Creating virtual environment for E2E tests...")
        if os.path.exists(venv_path):
            shutil.rmtree(venv_path)
        venv.create(venv_path, with_pip=True)
    
    # Install requirements
    print("Installing requirements...")
    pip_cmd = [python_exe, '-m', 'pip', 'install', '-r', 
               os.path.join(os.path.dirname(__file__), 'requirements.txt')]
    subprocess.run(pip_cmd, check=True)
    
    # Run pytest
    print("Running E2E tests...")
    pytest_cmd = [python_exe, '-m', 'pytest',
                  '--cov=packages/opal-client',
                  '--cov=packages/opal-server',
                  '--cov-report=term-missing',
                  os.path.dirname(__file__)]
    subprocess.run(pytest_cmd, check=True)

if __name__ == '__main__':
    main()
