#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Development helper script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

case "${1:-help}" in
    setup)
        echo "Setting up development environment..."
        python3 -m venv "${PROJECT_DIR}/.venv"
        source "${PROJECT_DIR}/.venv/bin/activate"
        pip install -r "${PROJECT_DIR}/addon/fall_detector/requirements.txt"
        pip install -r "${PROJECT_DIR}/addon/fall_detector/requirements-test.txt"
        pip install -r "${PROJECT_DIR}/tests/requirements-test.txt"
        pip install ruff yamllint pre-commit
        pre-commit install
        echo "Development environment ready."
        ;;
    test)
        echo "Running all tests..."
        pytest "${PROJECT_DIR}/addon/fall_detector/tests/" -v
        pytest "${PROJECT_DIR}/tests/integration/" -v
        ;;
    lint)
        echo "Running linters..."
        ruff check "${PROJECT_DIR}"
        ruff format --check "${PROJECT_DIR}"
        yamllint -c "${PROJECT_DIR}/.yamllint" "${PROJECT_DIR}"
        ;;
    format)
        echo "Formatting code..."
        ruff check --fix "${PROJECT_DIR}"
        ruff format "${PROJECT_DIR}"
        ;;
    docker-build)
        echo "Building add-on Docker image..."
        docker build \
            -t fall-detector-addon:dev \
            --build-arg BUILD_ARCH=amd64 \
            "${PROJECT_DIR}/addon/fall_detector/"
        ;;
    docker-run)
        echo "Running add-on in Docker..."
        docker run --rm -it \
            -p 8099:8099 \
            -v "${PROJECT_DIR}/addon/fall_detector/test-options.json:/data/options.json:ro" \
            fall-detector-addon:dev
        ;;
    help|*)
        echo "Usage: $0 {setup|test|lint|format|docker-build|docker-run}"
        ;;
esac
