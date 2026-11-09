FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# Wine lets this Linux Codespace run Windows Python and PyInstaller for local
# Windows builds. i386 is required by Debian's wine32 package.
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        unzip \
        file \
        wine \
        wine64 \
        wine32 \
        xvfb \
        xauth \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Trigger rebuild prompt check
