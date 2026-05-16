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

# Copy application code
COPY app/ /app/app/

# Copy entrypoint
COPY run.sh /run.sh
RUN chmod a+x /run.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://127.0.0.1:8099/health || exit 1

CMD [ "/run.sh" ]
