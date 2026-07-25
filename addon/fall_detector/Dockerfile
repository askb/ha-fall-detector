# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation
ARG BUILD_FROM
FROM ${BUILD_FROM}

LABEL maintainer="Anil Belur <askb23@gmail.com>"
LABEL org.opencontainers.image.title="Fall Detector Add-on"
LABEL org.opencontainers.image.description="AI-powered elderly fall detection for Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/askb/ha-fall-detector"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Install system dependencies (Debian bookworm)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        python3 \
        python3-pip \
        python3-venv \
        python3-numpy \
        python3-opencv \
        python3-pil \
        libopenblas0 \
        libjpeg62-turbo \
        libpng16-16 \
        libtiff6 \
        libwebp7 \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (use --break-system-packages for Debian 12+)
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages --prefer-binary \
    -r /app/requirements.txt

# Pre-bake pose models so the add-on works without first-boot internet
# (tfhub.dev is dead). Pinned to an immutable commit + verified checksums.
ARG MOVENET_REPO=https://github.com/yuanoook/tf-movenet-files-hub/raw/32fa5c49223b8ff4279a46b3e6ff211f2ca9f31e
RUN mkdir -p /app/models \
    && curl -sfL -o /app/models/movenet_lightning.tflite \
        "${MOVENET_REPO}/singlepose-lightning-tflite-int8.tflite" \
    && curl -sfL -o /app/models/movenet_thunder.tflite \
        "${MOVENET_REPO}/singlepose-thunder-tflite-int8.tflite" \
    && echo "cd7cc22fa946e5d146a7b98d496853e1923e22828d3972d579973f27f91bb105  /app/models/movenet_lightning.tflite" | sha256sum -c - \
    && echo "b72fed22707cd6fb94b5a248b9bddb9c062b9f445471b4fa263407cf6d222011  /app/models/movenet_thunder.tflite" | sha256sum -c -

# Copy application code
COPY app/ /app/app/

# Copy entrypoint
COPY run.sh /run.sh
RUN chmod a+x /run.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://127.0.0.1:8099/health || exit 1

CMD [ "/run.sh" ]
