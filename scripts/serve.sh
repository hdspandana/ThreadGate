#!/usr/bin/env bash
# Start the Streamlit demo, reinstalling dependencies first if they are missing.
# The sandbox this was developed in does not persist installed packages between
# sessions, so this is safe to run every time.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! python3 -c "import streamlit" 2>/dev/null; then
  echo "installing dependencies..."
  python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
fi

exec python3 -m streamlit run app/streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port "${PORT:-8501}" \
  --server.headless true \
  --browser.gatherUsageStats false
