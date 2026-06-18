"""Ensure the repo root is importable so tests can `import aria` when run via pytest."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
