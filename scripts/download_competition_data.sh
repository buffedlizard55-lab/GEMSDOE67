#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
"${PYTHON:-.venv/bin/python}" scripts/restore_data.py
