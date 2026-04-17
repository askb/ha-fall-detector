#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run all linters
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Ruff Lint ==="
ruff check "${PROJECT_DIR}"

echo "=== Ruff Format Check ==="
ruff format --check "${PROJECT_DIR}"

echo "=== YAML Lint ==="
yamllint -c "${PROJECT_DIR}/.yamllint" "${PROJECT_DIR}"

echo "=== All linters passed ==="
