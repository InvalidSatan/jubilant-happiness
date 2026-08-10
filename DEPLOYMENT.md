# Deployment Guide — Octagon Log

Complete steps for hosting the application on the university network with PostgreSQL, accessible to faculty and monitors over HTTPS.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Server Prerequisites](#2-server-prerequisites)
3. [PostgreSQL Database Setup](#3-postgresql-database-setup)
4. [Application Setup](#4-application-setup)
5. [Initialize the Database](#5-initialize-the-database)
6. [Configure the Application](#6-configure-the-application)
7. [Start the Application](#7-start-the-application)
8. [Reverse Proxy with Nginx](#8-reverse-proxy-with-nginx)
9. [Keep It Running with systemd](#9-keep-it-running-with-systemd)
10. [Network Access & Firewall](#10-network-access--firewall)
11. [Automated Backups](#11-automated-backups)
12. [Post-Deployment Checklist](#12-post-deployment-checklist)
13. [Creating Faculty & Monitor Accounts](#13-creating-faculty--monitor-accounts)
14. [Maintenance & Updates](#14-maintenance--updates)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Overview

```
                 University Network
                        │
         ┌──────────────┴──────────────┐
         │        Nginx (443/HTTPS)    │
         │  ssl termination + proxy    │
         └──────────────┬──────────────┘
                        │ proxy_pass :8080
         ┌──────────────┴──────────────┐
         │     Gunicorn (8080)         │
         │  Flask app  ×  2 workers    │
         └──────────────┬──────────────┘
                        │
         ┌──────────────┴──────────────┐
         │     PostgreSQL (5432)       │
         │  woodshop_log database      │
         │  local socket, always on    │
         └─────────────────────────────┘
```

**Why PostgreSQL instead of SQLite:**

| Concern | SQLite | PostgreSQL |
|---|---|---|
| Concurrent users | Single writer, blocks under load | Hundreds of concurrent read/write |
| Data durability | File-level, no crash recovery | WAL + point-in-time recovery |
| Backups while running | Must copy file (risk of corruption) | `pg_dump` is safe during writes |
| Connection pooling | N/A | Built-in, tunable |
| Network access | File on disk only | TCP socket, can separate DB server later |
| University IT standards | Not typical for production | Standard, well-supported |

---

## 2. Server Prerequisites

Request a Linux VM from university IT (or use an existing departmental server).

**Minimum specs:**
- Ubuntu 22.04 LTS or RHEL 8+ (any modern Linux)
- 2 CPU cores, 2 GB RAM (handles hundreds of concurrent users)
- 20 GB disk (database will be tiny — years of logs fit in < 1 GB)
- Network access on ports 80 and 443 (or just 443)
- A DNS name (e.g., `shoplog.art.appstate.edu`) — request from IT

**Install system packages (Ubuntu/Debian):**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    postgresql postgresql-contrib \
                    nginx certbot python3-certbot-nginx \
                    git
```

**Install system packages (RHEL/Rocky):**

```bash
sudo dnf install -y python3 python3-pip \
                    postgresql-server postgresql-contrib \
                    nginx certbot python3-certbot-nginx \
                    git
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
```

Verify versions:

```bash
python3 --version   # 3.11+
psql --version      # 14+
nginx -v            # 1.18+
```

---

## 3. PostgreSQL Database Setup

### 3a. Create the database and user

```bash
# Switch to the postgres system user
sudo -u postgres psql
```

Run the following SQL inside the `psql` prompt:

```sql
-- Create a dedicated database user
CREATE USER woodshop WITH PASSWORD 'PICK_A_STRONG_PASSWORD_HERE';

-- Create the database owned by that user
CREATE DATABASE woodshop_log OWNER woodshop;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE woodshop_log TO woodshop;

-- Exit
\q
```

> **IMPORTANT:** Replace `PICK_A_STRONG_PASSWORD_HERE` with a real password.
> Generate one with: `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`

### 3b. Allow local password authentication

Edit the PostgreSQL client auth config:

```bash
sudo nano /etc/postgresql/*/main/pg_hba.conf    # Ubuntu/Debian
# or
sudo nano /var/lib/pgsql/data/pg_hba.conf        # RHEL/Rocky
```

Ensure there is a line that allows local password auth for the `woodshop` user. Add or confirm:

```
# TYPE  DATABASE        USER        ADDRESS         METHOD
local   woodshop_log    woodshop                    scram-sha-256
host    woodshop_log    woodshop    127.0.0.1/32    scram-sha-256
```

Restart PostgreSQL:

```bash
sudo systemctl restart postgresql
```

### 3c. Verify the connection

```bash
psql -U woodshop -d woodshop_log -h 127.0.0.1 -c "SELECT 1;"
```

You should see a result of `1`. If this fails, check the password and `pg_hba.conf`.

### 3d. PostgreSQL performance tuning (optional)

Edit `/etc/postgresql/*/main/postgresql.conf` for a small-to-medium workload:

```ini
# Memory
shared_buffers = 256MB          # 25% of RAM, up to 512MB
effective_cache_size = 1GB      # 50-75% of RAM
work_mem = 16MB

# WAL / Durability
wal_level = replica
max_wal_size = 1GB
checkpoint_completion_target = 0.9

# Connections
max_connections = 50            # App uses pool_size=5 per worker, plenty of headroom
```

Restart after changes: `sudo systemctl restart postgresql`

---

## 4. Application Setup

### 4a. Create a service user

```bash
sudo useradd -r -m -s /bin/bash woodshop
sudo su - woodshop
```

### 4b. Clone the repository

```bash
cd /home/woodshop
git clone <repo-url> jubilant-happiness
cd jubilant-happiness
```

### 4c. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Verify PostgreSQL driver is installed:

```bash
python3 -c "import psycopg2; print('psycopg2 OK:', psycopg2.__version__)"
```

---

## 5. Initialize the Database

### 5a. Configure the environment

```bash
cp .env.example .env
nano .env
```

Set these values in `.env`:

```bash
# REQUIRED — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<your-generated-secret-key>

# REQUIRED — must match the user/password/database from Step 3a
DATABASE_URL=postgresql://woodshop:PICK_A_STRONG_PASSWORD_HERE@localhost:5432/woodshop_log

PORT=8080
WORKERS=2
```

### 5b. Apply migrations

Create (or upgrade) the schema via Flask-Migrate. This creates every table and seeds the five baseline shop areas:

```bash
source venv/bin/activate
export FLASK_APP=run.py
flask db upgrade
```

**If this is an upgrade from a pre-migration deploy** (a deploy where the database was originally created via `db.create_all()` before `migrations/` landed in the repo), Alembic has no version record and will try to re-create existing tables. Stamp the database as already-at-head once, then run `upgrade` normally on future releases:

```bash
flask db stamp head
# subsequent releases:
flask db upgrade
```

### 5c. Run the production seed

This creates equipment certifications and prompts you to set up real admin accounts (no sample/test data):

```bash
python seed_production.py
```

You will be prompted to create:
1. **Primary faculty admin** — the first faculty account (can create other faculty)
2. **Admin monitor** — the first monitor account (can create other monitors)

> Use real names, real AppState emails, and strong passwords (8+ characters).

### 5d. Verify tables were created

```bash
psql -U woodshop -d woodshop_log -h 127.0.0.1 -c "\dt"
```

You should see tables: `alembic_version`, `shop_area`, `equipment`, `monitor`, `faculty`, `student`, `warning`, `monitor_session`, `student_visit`, `monitor_areas`, `student_training`.

The `alembic_version` table is maintained by Flask-Migrate and tracks which migration revision the database is currently at.

---

## 6. Configure the Application

The full `.env` file for production:

```bash
# --- REQUIRED ---
SECRET_KEY=<64-char-hex-string>
DATABASE_URL=postgresql://woodshop:YOUR_PASSWORD@localhost:5432/woodshop_log

# --- Server ---
PORT=8080
WORKERS=2

# --- Database pool (defaults are fine for most deployments) ---
# DB_POOL_SIZE=5          # persistent connections per worker
# DB_MAX_OVERFLOW=10      # extra connections under burst load
# DB_POOL_TIMEOUT=30      # seconds to wait for a connection
# DB_POOL_RECYCLE=1800    # recycle connections every 30 minutes

# --- Integrations (configure when ready) ---
# BANNER_API_URL=https://banner.appstate.edu/api
# BANNER_API_KEY=
# ASULEARN_API_URL=https://asulearn.appstate.edu/webservice/rest/server.php
# ASULEARN_API_TOKEN=
```

**Connection pool math:** With `WORKERS=2` and `DB_POOL_SIZE=5`, the app maintains 10 persistent database connections plus up to 20 overflow — easily handles 100+ concurrent users.

---

## 7. Start the Application

Quick test to verify it starts:

```bash
source venv/bin/activate
./start.sh
```

Verify: `curl http://localhost:8080` should return HTML. Press Ctrl+C to stop.

---

## 8. Reverse Proxy with Nginx

### 8a. Create the Nginx site config

```bash
sudo nano /etc/nginx/sites-available/shoplog
```

```nginx
# Redirect HTTP → HTTPS
server {
    listen 80;
    server_name shoplog.art.appstate.edu;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name shoplog.art.appstate.edu;

    # --- TLS certificates ---
    # Option A: University-issued certificate (get from IT)
    ssl_certificate     /etc/ssl/certs/shoplog.art.appstate.edu.pem;
    ssl_certificate_key /etc/ssl/private/shoplog.art.appstate.edu.key;

    # Option B: Let's Encrypt (if DNS is public)
    # Run: sudo certbot --nginx -d shoplog.art.appstate.edu
    # Certbot will fill in the ssl lines automatically.

    # --- Security headers ---
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy strict-origin-when-cross-origin;

    # --- Proxy to Gunicorn ---
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout for long CSV exports
        proxy_read_timeout 120s;
    }

    # --- Static files (optional, small performance gain) ---
    # If you add a static/ directory later:
    # location /static/ {
    #     alias /home/woodshop/jubilant-happiness/app/static/;
    #     expires 7d;
    # }
}
```

### 8b. Enable and test

```bash
sudo ln -s /etc/nginx/sites-available/shoplog /etc/nginx/sites-enabled/
sudo nginx -t          # verify config
sudo systemctl reload nginx
```

---

## 9. Keep It Running with systemd

### 9a. Create the service file

```bash
sudo nano /etc/systemd/system/woodshop-log.service
```

```ini
[Unit]
Description=Octagon Log
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=exec
User=woodshop
Group=woodshop
WorkingDirectory=/home/woodshop/jubilant-happiness
EnvironmentFile=/home/woodshop/jubilant-happiness/.env
ExecStart=/home/woodshop/jubilant-happiness/venv/bin/gunicorn wsgi:app \
    --bind 127.0.0.1:8080 \
    --workers 2 \
    --access-logfile /var/log/woodshop-log/access.log \
    --error-logfile /var/log/woodshop-log/error.log \
    --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 9b. Create log directory and enable

```bash
sudo mkdir -p /var/log/woodshop-log
sudo chown woodshop:woodshop /var/log/woodshop-log

sudo systemctl daemon-reload
sudo systemctl enable woodshop-log
sudo systemctl start woodshop-log
sudo systemctl status woodshop-log
```

### 9c. View logs

```bash
# Application logs
sudo journalctl -u woodshop-log -f

# Access log
tail -f /var/log/woodshop-log/access.log
```

---

## 10. Network Access & Firewall

### 10a. Firewall rules (UFW on Ubuntu)

```bash
sudo ufw allow 443/tcp    # HTTPS
sudo ufw allow 80/tcp     # HTTP (redirects to HTTPS)
sudo ufw enable
sudo ufw status
```

### 10b. Restricting access to university network only

If the app should only be reachable from on-campus (including VPN), configure the firewall to only allow the university IP ranges:

```bash
# Example: only allow from AppState's IP range (get exact ranges from IT)
sudo ufw delete allow 443/tcp
sudo ufw allow from 152.10.0.0/16 to any port 443
sudo ufw allow from 10.0.0.0/8 to any port 443     # VPN/internal range
```

Alternatively, restrict at the Nginx level (keeps the firewall open but Nginx rejects outside traffic):

```nginx
# Add inside the server block
allow 152.10.0.0/16;    # Campus network
allow 10.0.0.0/8;       # VPN / internal
deny all;
```

### 10c. PostgreSQL — keep it local only

PostgreSQL should only listen on localhost. Verify in `postgresql.conf`:

```ini
listen_addresses = 'localhost'    # This is the default — do NOT change to '*'
```

The database is never exposed to the network. Only the application on the same server connects to it.

---

## 11. Automated Backups

### 11a. Database backup script

```bash
sudo nano /home/woodshop/backup-db.sh
```

```bash
#!/bin/bash
# Backup Octagon Log PostgreSQL database
BACKUP_DIR="/home/woodshop/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/woodshop_log_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

# pg_dump is safe to run while the database is in use
PGPASSWORD="YOUR_DB_PASSWORD" pg_dump -U woodshop -h 127.0.0.1 woodshop_log \
    | gzip > "$BACKUP_FILE"

# Keep only the last 30 backups
ls -t "$BACKUP_DIR"/woodshop_log_*.sql.gz | tail -n +31 | xargs -r rm

echo "Backup complete: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
```

```bash
chmod +x /home/woodshop/backup-db.sh
```

> **Tip:** Instead of storing the password in the script, create a `~/.pgpass` file:
> ```
> localhost:5432:woodshop_log:woodshop:YOUR_DB_PASSWORD
> ```
> `chmod 600 ~/.pgpass` — then remove the `PGPASSWORD=` from the script.

### 11b. Schedule nightly backups with cron

```bash
sudo crontab -u woodshop -e
```

Add:

```
# Nightly database backup at 2:00 AM
0 2 * * * /home/woodshop/backup-db.sh >> /home/woodshop/backups/backup.log 2>&1
```

### 11c. Restoring from a backup

```bash
# Drop and recreate the database
sudo -u postgres psql -c "DROP DATABASE woodshop_log;"
sudo -u postgres psql -c "CREATE DATABASE woodshop_log OWNER woodshop;"

# Restore
gunzip -c /home/woodshop/backups/woodshop_log_20260225_020000.sql.gz \
    | psql -U woodshop -h 127.0.0.1 woodshop_log
```

---

## 12. Post-Deployment Checklist

Run through this after the app is live:

- [ ] **Access the app** at `https://shoplog.art.appstate.edu` — login page loads
- [ ] **Log in as faculty admin** — verify the account created during seed works
- [ ] **Log in as admin monitor** — verify dashboard loads
- [ ] **Change default passwords** — if you used `seed.py` (dev seeder) instead of `seed_production.py`, change ALL passwords immediately
- [ ] **Create real faculty accounts** — faculty admin can add other instructors via Faculty Portal > Faculty Accounts
- [ ] **Create real monitor accounts** — admin monitor (or faculty admin) creates student employee accounts via the admin panel
- [ ] **Upload students** — faculty admin can bulk-upload students via CSV at `/faculty/upload-students`
- [ ] **Verify HTTPS** — confirm the padlock icon and that HTTP redirects to HTTPS
- [ ] **Verify backups** — run `backup-db.sh` manually and check the output
- [ ] **Verify auto-restart** — `sudo systemctl restart woodshop-log` and confirm it comes back
- [ ] **Test from another machine** — access the URL from a different campus computer

---

## 13. Creating Faculty & Monitor Accounts

### Faculty accounts

1. Log in at `https://shoplog.art.appstate.edu/faculty/login`
2. Go to **Faculty Accounts** (only visible to the primary admin)
3. Click **Add Faculty Account**
4. Fill in username, display name, email, password
5. Optionally check "Primary Admin" to give full management access

### Monitor accounts

Monitors can be created by the admin monitor (Admin panel) or by a primary faculty admin (Faculty portal):

1. Go to **Monitors** section
2. Click **Add Monitor**
3. Fill in username, display name, password
4. Assign one or more shop areas
5. Optionally check "Admin" for full admin access

### Bulk student upload

1. Faculty login > **Upload Students**
2. Prepare a CSV file with columns: `student_id`, `name`, `email`
3. Upload — the system handles flexible column name mapping

---

## 14. Maintenance & Updates

### Updating the application

```bash
sudo su - woodshop
cd jubilant-happiness
source venv/bin/activate

# Pull latest code
git pull origin master

# Install any new dependencies
pip install -r requirements.txt

# Apply any new database migrations
export FLASK_APP=run.py
flask db upgrade

# Restart the service
exit
sudo systemctl restart woodshop-log
```

> Schema changes are managed by Flask-Migrate (Alembic). Every release that touches the models ships a new file under `migrations/versions/`, and `flask db upgrade` applies any that haven't been run yet. You can preview what's pending with `flask db current` and `flask db history`.

### Monitoring health

```bash
# Is the service running?
sudo systemctl status woodshop-log

# Recent application logs
sudo journalctl -u woodshop-log --since "1 hour ago"

# PostgreSQL status
sudo systemctl status postgresql

# Database size
psql -U woodshop -h 127.0.0.1 woodshop_log -c "SELECT pg_size_pretty(pg_database_size('woodshop_log'));"

# Active database connections
psql -U woodshop -h 127.0.0.1 woodshop_log -c "SELECT count(*) FROM pg_stat_activity WHERE datname='woodshop_log';"
```

### Log rotation

Add log rotation for the Gunicorn logs:

```bash
sudo nano /etc/logrotate.d/woodshop-log
```

```
/var/log/woodshop-log/*.log {
    daily
    missingok
    rotate 14
    compress
    notifempty
    create 0640 woodshop woodshop
    postrotate
        systemctl reload woodshop-log > /dev/null 2>&1 || true
    endscript
}
```

---

## 15. Troubleshooting

### "SECRET_KEY environment variable must be set"

The `.env` file is missing or `SECRET_KEY` is not set. Verify:

```bash
cat /home/woodshop/jubilant-happiness/.env | grep SECRET_KEY
```

### "could not connect to server: Connection refused"

PostgreSQL is not running or the `DATABASE_URL` is wrong.

```bash
sudo systemctl status postgresql
psql -U woodshop -d woodshop_log -h 127.0.0.1 -c "SELECT 1;"
```

### "FATAL: password authentication failed"

The password in `DATABASE_URL` doesn't match what was set in PostgreSQL. Reset it:

```bash
sudo -u postgres psql -c "ALTER USER woodshop WITH PASSWORD 'new_password_here';"
```

Then update `DATABASE_URL` in `.env` and restart: `sudo systemctl restart woodshop-log`

### "502 Bad Gateway" from Nginx

Gunicorn isn't running or is on a different port.

```bash
sudo systemctl status woodshop-log
curl http://127.0.0.1:8080     # test Gunicorn directly
```

### Database seems slow

Check connection count and long-running queries:

```bash
psql -U woodshop -h 127.0.0.1 woodshop_log -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE datname = 'woodshop_log' AND state != 'idle'
ORDER BY duration DESC;
"
```

### Need to reset everything and start fresh

```bash
sudo systemctl stop woodshop-log
sudo -u postgres psql -c "DROP DATABASE woodshop_log;"
sudo -u postgres psql -c "CREATE DATABASE woodshop_log OWNER woodshop;"
cd /home/woodshop/jubilant-happiness
source venv/bin/activate
python seed_production.py
sudo systemctl start woodshop-log
```
