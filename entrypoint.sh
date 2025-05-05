#!/usr/bin/env bash
set -e

# Entrypoint script for Docker Compose: choose between dev or prod mode
# Usage: ./entrypoint.sh [-dev|-prod]

# Validate and configure DATA_DIR
VALID=false
if [ "$1" = "-dev" ]; then
  DATA_DIR="$HOME/app_data/TemPrice/instance"
  VALID=true
elif [ "$1" = "-prod" ]; then
  DATA_DIR="/root/app_data/TemPrice/instance"
  VALID=true
else
  echo "Usage: $0 [-dev|-prod]"
  echo "  -dev   → use ~/app_data/TemPrice/instance"
  echo "  -prod  → use /root/app_data/TemPrice/instance"
fi

# Only proceed if a valid mode was given
if [ "$VALID" = true ]; then
  # Ensure the data directory exists
#   mkdir -p "$DATA_DIR"

  # Export for Docker Compose interpolation
  export DATA_DIR

  # Launch Docker Compose
  docker-compose up -d --build
fi
