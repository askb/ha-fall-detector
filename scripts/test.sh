#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run all tests
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Add-on Unit Tests ==="
pytest "${PROJECT_DIR}/addon/fall_detector/tests/" -v --tb=short

echo "=== Integration Tests ==="
pytest "${PROJECT_DIR}/tests/integration/" -v --tb=short

echo "=== All tests passed ==="
