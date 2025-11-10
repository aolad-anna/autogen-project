#!/bin/bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "Setup complete. Run with: python src/autogen_project.py"
