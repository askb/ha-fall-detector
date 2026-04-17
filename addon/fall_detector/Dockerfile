# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation
ARG BUILD_FROM
FROM ${BUILD_FROM}

LABEL maintainer="Anil Belur <askb23@gmail.com>"
LABEL org.opencontainers.image.title="Fall Detector Add-on"
LABEL org.opencontainers.image.description="AI-powered elderly fall detection for Home Assistant"
LABEL org.opencontainers.image.source="https://github.com/askb/ha-fall-detector"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Install system dependencies needed for OpenCV, numpy, and TFLite
RUN apk add --no-cache \
        curl \
        py3-opencv \
        py3-numpy \
        py3-pillow \
        libstdc++ \
        libjpeg-turbo \
        libpng \
        tiff \
        libwebp \
        openblas \
    && apk add --no-cache --virtual .build-deps \
        build-base \
        python3-dev \
        openblas-dev \
        gfortran

# Copy and install Python dependencies first (layer caching)
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --prefer-binary -r /app/requirements.txt \
    && apk del .build-deps

# Copy application code and models
COPY app/ /app/app/
COPY models/ /app/models/

# Copy entrypoint
COPY run.sh /run.sh
RUN chmod a+x /run.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://127.0.0.1:8099/health || exit 1

CMD [ "/run.sh" ]
