# Octagon Log — production container image
#
#   docker build -t octagon-log .
#   docker run --env-file .env -p 8080:8080 octagon-log
#
# Gunicorn serves the `app` instance defined in wsgi.py — the WSGI target is
# `wsgi:app`. wsgi.py defaults FLASK_CONFIG to "production", which requires
# SECRET_KEY to be set or the app refuses to boot.
#
# Migrations are deliberately NOT run at startup: two containers starting at
# once would race on the same `flask db upgrade`. Run it as a one-off step
# instead — see "Appendix A" in DEPLOYMENT.md.

FROM python:3.12-slim

# No .pyc files, and unbuffered stdout/stderr so Gunicorn's logs show up in
# `docker logs` as they happen rather than when a buffer fills.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    FLASK_APP=run.py

WORKDIR /app

# Dependencies before application code, so editing the app doesn't invalidate
# the install layer. PyMySQL is pure Python, so this needs no compiler and no
# MySQL client headers.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run unprivileged. `instance/` is gitignored, so it never arrives via COPY —
# create it here, otherwise a deployment left on the default SQLite URL has
# nowhere to write its database file.
RUN useradd --create-home --shell /usr/sbin/nologin octagon \
    && mkdir -p instance \
    && chown -R octagon:octagon /app
USER octagon

# Documentation only — the listening port follows $PORT (see gunicorn.conf.py).
EXPOSE 8080

# /login is the cheapest unauthenticated GET route. urllib keeps curl and wget
# out of the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/login' % os.environ.get('PORT', '8080'), timeout=4)"]

CMD ["gunicorn", "wsgi:app", "--config", "gunicorn.conf.py"]
