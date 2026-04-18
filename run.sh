#!/bin/zsh
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Missing .venv. Run: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

exec .venv/bin/python -m streamlit run app.py
