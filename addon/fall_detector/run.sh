#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation
set -euo pipefail

CONFIG_PATH=/data/options.json

echo "--- Fall Detector Add-on Starting ---"
echo "Reading configuration from ${CONFIG_PATH}"

# Export config as environment variables for the Python app
export FALL_DETECTOR_CONFIG_PATH="${CONFIG_PATH}"
export FALL_DETECTOR_DATA_PATH="/data"
export FALL_DETECTOR_SHARE_PATH="/share/fall_detector"
export FALL_DETECTOR_MEDIA_PATH="/media/fall_detector"

# Create storage directories
mkdir -p "${FALL_DETECTOR_SHARE_PATH}" "${FALL_DETECTOR_MEDIA_PATH}"
mkdir -p "${FALL_DETECTOR_DATA_PATH}/models"
mkdir -p "${FALL_DETECTOR_DATA_PATH}/state"

echo "Starting Fall Detector service..."
exec python3 -m app.main
