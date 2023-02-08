#!/usr/bin/env python3

import os
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if "username for" in sys.argv[1].lower():
            print(os.environ["GIT_USERNAME"])
        elif "password for" in sys.argv[1].lower():
            print(os.environ["GIT_PASSWORD"])
