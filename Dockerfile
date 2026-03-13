FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# System dependencies
RUN apt-get update && apt-get install -y \
    curl gnupg build-essential git unzip sudo nano wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22.x LTS
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs

# Create clawdbot directory
RUN mkdir -p /root/.clawdbot

# Working directory
WORKDIR /root

# Copy Memory Kit (will be mounted as volume instead)
# COPY memory/ /root/.clawdbot/memory/

EXPOSE 18789

# Keep container running for interactive use
CMD ["bash"]
