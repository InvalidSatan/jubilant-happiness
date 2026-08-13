"""Gunicorn settings for the container image.

Loaded by `gunicorn wsgi:app --config gunicorn.conf.py` (see the Dockerfile).

Every value reads from the environment so the same image runs unchanged in the
department's beta deployment and on university hosting. The variable names
match .env.example — PORT and WORKERS — so one .env drives both ./start.sh and
the container.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = int(os.environ.get("WORKERS", "2"))

# Matches the timeout start.sh uses. Report exports over a full semester are
# the slowest requests the app serves.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))

# Log to stdout/stderr and let the container runtime collect them, rather than
# writing files inside an ephemeral filesystem.
accesslog = "-"
errorlog = "-"

# Gunicorn only honours X-Forwarded-* headers from the peers listed here. The
# default of 127.0.0.1 is correct for the systemd deployment, where Nginx and
# Gunicorn share a host, but NOT for a container: the proxy arrives as the
# bridge gateway or a pod address instead. Set this to the proxy's address in
# the deployment environment. "*" trusts whatever connects, which is only safe
# when nothing but the proxy can reach the container's port.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
