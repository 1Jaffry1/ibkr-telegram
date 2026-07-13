#!/bin/bash
cd "$(dirname "$0")"

# Settings now live inside the companion window.
# Keep this launcher as a convenience alias.
exec "$(dirname "$0")/mac_alerts.command"
