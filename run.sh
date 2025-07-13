#!/bin/bash
# Simple runner script for Code Route

source .venv/bin/activate
python -m code_route.cli "$@"