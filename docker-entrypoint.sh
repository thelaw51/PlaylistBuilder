#!/bin/sh
set -e
# Copy the default beets config into the volume on first run.
# Subsequent runs leave any user-modified config in place.
if [ ! -f /config/beets/config.yaml ]; then
    mkdir -p /config/beets
    cp /app/config/beets/config.yaml /config/beets/config.yaml
fi
exec "$@"
