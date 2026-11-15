#!/usr/bin/env bash
# Runs once when the codespace is created. Mirrors the CI install so the
# environment matches the one the results were checked in.
set -euo pipefail

pipx install uv
uv sync --locked --extra dev --extra llm --python 3.12
.venv/bin/hindcast build

cd web
npm ci
npm run build
