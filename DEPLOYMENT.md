# Deployment Guide — Octagon Log

Complete steps for hosting the application on the university network against the departmental MySQL Galera cluster, accessible to faculty and monitors over HTTPS.

> **Secrets come from the environment.** Every credential the app reads —
> `SECRET_KEY`, `DATABASE_URL`, and the integration tokens — is read with
> `os.getenv()` at startup and has no in-repo default. Nothing secret is
> committed. Under the container deployment, ITS injects these as environment
> variables; on a plain VM they come from `.env`.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Server Prerequisites](#2-server-prerequisites)
3. [MySQL Galera Database Setup](#3-mysql-galera-database-setup)
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

- [Appendix A — Running in a Container](#appendix-a--running-in-a-container)

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
         │   MySQL Galera cluster      │
         │   (3306, via load balancer) │
         │   octagon_log database      │
         │   managed by ITS            │
         └─────────────────────────────┘
```

The database is **not** installed on the application server. It is the
departmental MySQL Galera cluster, which ITS runs and backs up; the app
reaches it over the network with credentials supplied as environment
variables.

**Why the Galera cluster instead of SQLite:**

| Concern | SQLite | MySQL Galera |
|---|---|---|
| Concurrent users | Single writer, blocks under load | Hundreds of concurrent read/write |
| Data durability | File-level, no crash recovery | Synchronous replication across nodes |
| Availability | Dies with the app server | Survives a node failure |
| Backups while running | Must copy file (risk of corruption) | Handled by ITS on the cluster |
| Connection pooling | N/A | Built-in, tunable |
| Network access | File on disk only | TCP, app and database scale separately |
| University IT standards | Not typical for production | Standard, ITS-supported |

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
                    mysql-client \
                    nginx certbot python3-certbot-nginx \
                    git
```

**Install system packages (RHEL/Rocky):**

```bash
sudo dnf install -y python3 python3-pip \
                    mysql \
                    nginx certbot python3-certbot-nginx \
                    git
```

Only the MySQL **client** is needed — the server lives on the Galera cluster.
The app's driver (PyMySQL) is pure Python, so there are no database header
packages or compilers to install.

Verify versions:

```bash
python3 --version   # 3.11+
mysql --version     # 8.0+
nginx -v            # 1.18+
```

Confirm the app server can reach the cluster (ask ITS to open the path if not):

```bash
nc -zv galera.its.appstate.edu 3306
```

---

## 3. MySQL Galera Database Setup

The cluster is managed by ITS, so this section is mostly *requesting* the
right thing rather than installing it.

### 3a. What to request from ITS

Ask for a database and a dedicated user on the Galera cluster:

```sql
-- Run by the cluster DBA, on one node (Galera replicates it to the rest)
CREATE DATABASE octagon_log
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

CREATE USER 'octagon'@'%' IDENTIFIED BY 'STRONG_PASSWORD_HERE';

GRANT ALL PRIVILEGES ON octagon_log.* TO 'octagon'@'%';
FLUSH PRIVILEGES;
```

Two details matter and are easy to get wrong:

- **`utf8mb4`, not `utf8`.** MySQL's legacy `utf8` is a three-byte encoding
  that cannot represent emoji or many non-Latin names. Student names and care
  notes are free text, so a `utf8` database will throw
  *"Incorrect string value"* on perfectly ordinary input.
- **The app needs `ALTER`/`CREATE`/`DROP`, not just DML.** Schema changes ship
  as Alembic migrations that run against this database. If ITS prefers to keep
  DDL rights off the runtime account, request a second account for migrations
  and run `flask db upgrade` with that one.

### 3b. Application account privileges

The app's own connection needs `SELECT, INSERT, UPDATE, DELETE` on
`octagon_log.*`. Grant `CREATE, ALTER, DROP, INDEX, REFERENCES` as well if the
same account will run migrations.

### 3c. Verify the connection

From the application server (or a container in the same network):

```bash
mysql -h galera.its.appstate.edu -P 3306 -u octagon -p octagon_log -e "SELECT 1;"
```

You should see a result of `1`. Also confirm the character set came out right:

```bash
mysql -h galera.its.appstate.edu -u octagon -p -e \
  "SELECT default_character_set_name, default_collation_name
     FROM information_schema.schemata WHERE schema_name='octagon_log';"
```

Expect `utf8mb4` / `utf8mb4_unicode_ci`.

### 3d. Galera-specific caveats

Galera is multi-master synchronous replication, which differs from a single
MySQL server in ways that affect this app:

- **Route writes to one node.** When two nodes commit conflicting writes,
  Galera resolves it at commit time by aborting one with a deadlock error
  (`1213`). Point `DATABASE_URL` at the load balancer's single-writer VIP, or
  at one node, rather than round-robining writes across all three.
- **Every table needs a primary key.** Galera's row-based replication requires
  it. Every table in this schema already has one — keep it that way when adding
  models.
- **InnoDB only.** Galera does not replicate MyISAM. This is the MySQL 8
  default, so it only becomes a problem if someone overrides it.
- **Migrations briefly block the cluster.** Schema changes replicate under
  Total Order Isolation, which pauses writes cluster-wide while the DDL runs.
  The tables here are small enough that this is milliseconds, but run
  `flask db upgrade` during a quiet window anyway.
- **A failed migration does not roll back.** MySQL commits DDL implicitly, so
  unlike PostgreSQL a migration that dies halfway leaves the schema partly
  changed. Take a backup before upgrading and be prepared to fix forward.
- **Idle connections get dropped.** Both the load balancer and MySQL's
  `wait_timeout` will close idle connections out from under the pool. The app
  sets `pool_pre_ping` and `pool_recycle` (default 1800s) to cope; if the
  cluster's `wait_timeout` is lower than 1800, lower `DB_POOL_RECYCLE` to match.

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

Verify the MySQL driver is installed:

```bash
python3 -c "import pymysql; print('PyMySQL OK')"
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
DATABASE_URL=mysql://octagon:STRONG_PASSWORD_HERE@galera.its.appstate.edu:3306/octagon_log

PORT=8080
WORKERS=2
```

> The plain `mysql://` scheme is what you write. The app rewrites it to
> `mysql+pymysql://` at startup (SQLAlchemy would otherwise look for the
> MySQLdb C extension, which is not installed) and appends
> `?charset=utf8mb4` if you have not set a charset yourself. Writing
> `mysql+pymysql://` explicitly also works.

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
mysql -h galera.its.appstate.edu -u octagon -p octagon_log -e "SHOW TABLES;"
```

You should see tables: `alembic_version`, `shop_area`, `equipment`, `monitor`, `faculty`, `student`, `warning`, `monitor_session`, `student_visit`, `monitor_areas`, `student_training`.

The `alembic_version` table is maintained by Flask-Migrate and tracks which migration revision the database is currently at.

---

## 6. Configure the Application

The full `.env` file for production:

```bash
# --- REQUIRED ---
SECRET_KEY=<64-char-hex-string>
DATABASE_URL=mysql://octagon:YOUR_PASSWORD@galera.its.appstate.edu:3306/octagon_log

# --- Server ---
PORT=8080
WORKERS=2

# --- Database pool (defaults are fine for most deployments) ---
# DB_POOL_SIZE=5          # persistent connections per worker
# DB_MAX_OVERFLOW=10      # extra connections under burst load
# DB_POOL_TIMEOUT=30      # seconds to wait for a connection
# DB_POOL_RECYCLE=1800    # recycle connections every 30 minutes;
#                         # must stay below the cluster's wait_timeout
#                         # and the load balancer's idle timeout

# --- Integrations (configure when ready) ---
# BANNER_API_URL=https://banner.appstate.edu/api
# BANNER_API_KEY=
# ASULEARN_API_URL=https://asulearn.appstate.edu/webservice/rest/server.php
# ASULEARN_API_TOKEN=
```

**Connection pool math:** With `WORKERS=2` and `DB_POOL_SIZE=5`, the app maintains 10 persistent database connections plus up to 20 overflow — easily handles 100+ concurrent users. Note that the pool is *per process*: scaling to N containers or N Gunicorn workers multiplies the connection count, and the Galera cluster's `max_connections` is shared with every other application on it. Multiply before scaling up, and tell ITS the expected ceiling.

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
After=network.target

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

### 10c. Database access

The Galera cluster is reached over the network rather than a local socket, so
the database is no longer sealed off by "localhost only". Two things to confirm
with ITS:

- The cluster accepts connections **only** from the application servers'
  addresses (or the container network), not from campus at large.
- The `octagon` user is scoped as tightly as the cluster's policy allows —
  `'octagon'@'10.x.%'` rather than `'octagon'@'%'` where practical.

If the connection crosses an untrusted network segment, require TLS and point
the app at the CA bundle:

```bash
DATABASE_URL=mysql://octagon:PASSWORD@galera.its.appstate.edu:3306/octagon_log?ssl_ca=/etc/ssl/certs/ca-certificates.crt
```

Query parameters set this way are passed through to the driver — the app only
adds `charset` when you have not specified one.

---

## 11. Automated Backups

**Check with ITS first.** The Galera cluster is almost certainly backed up at
the cluster level already. The script below is an *application-level* dump —
useful as a pre-migration safety net and for restoring a single table without
involving the DBA, not as the primary backup.

### 11a. Database backup script

```bash
sudo nano /home/woodshop/backup-db.sh
```

```bash
#!/bin/bash
# Application-level dump of the Octagon Log database
BACKUP_DIR="/home/woodshop/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/octagon_log_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

# --single-transaction takes a consistent InnoDB snapshot without locking
# writers. Do NOT add --lock-tables against Galera: it stalls the cluster.
mysqldump --defaults-file=/home/woodshop/.my.cnf \
    --single-transaction --quick --routines --default-character-set=utf8mb4 \
    octagon_log | gzip > "$BACKUP_FILE"

# Keep only the last 30 backups
ls -t "$BACKUP_DIR"/octagon_log_*.sql.gz | tail -n +31 | xargs -r rm

echo "Backup complete: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
```

```bash
chmod +x /home/woodshop/backup-db.sh
```

> **Keep the password out of the script and off the process list.** Anything
> passed as `-pPASSWORD` is visible in `ps` to every user on the box. Put the
> credentials in `/home/woodshop/.my.cnf` instead:
> ```ini
> [client]
> host = galera.its.appstate.edu
> user = octagon
> password = YOUR_DB_PASSWORD
> ```
> then `chmod 600 /home/woodshop/.my.cnf`.

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

Restoring replicates to every node in the cluster, so stop the app first and
be certain of the dump you are restoring.

```bash
sudo systemctl stop woodshop-log

mysql --defaults-file=/home/woodshop/.my.cnf -e \
  "DROP DATABASE octagon_log;
   CREATE DATABASE octagon_log CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

gunzip -c /home/woodshop/backups/octagon_log_20260225_020000.sql.gz \
    | mysql --defaults-file=/home/woodshop/.my.cnf octagon_log

sudo systemctl start woodshop-log
```

> A large restore is a single enormous write set. If the dump is big enough to
> exceed the cluster's `wsrep_max_ws_size`, restore it in chunks or have the
> DBA restore it node-side instead.

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

# Can we reach the cluster?
mysql --defaults-file=/home/woodshop/.my.cnf -e "SELECT 1;"

# Database size
mysql --defaults-file=/home/woodshop/.my.cnf -e "
SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 1) AS size_mb
FROM information_schema.tables WHERE table_schema = 'octagon_log';"

# Active connections from this app
mysql --defaults-file=/home/woodshop/.my.cnf -e "
SELECT COUNT(*) FROM information_schema.processlist WHERE db = 'octagon_log';"

# Cluster health — size should equal the node count, status 'Primary'
mysql --defaults-file=/home/woodshop/.my.cnf -e "
SHOW STATUS WHERE Variable_name IN
  ('wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment');"
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

### "No module named 'MySQLdb'"

`DATABASE_URL` reached SQLAlchemy without the driver being rewritten — normally
because something bypassed `config.py` and built the engine directly. Write the
URL as `mysql+pymysql://...` explicitly, and confirm PyMySQL is installed:

```bash
python3 -c "import pymysql; print('PyMySQL OK')"
```

### "Can't connect to MySQL server on ... (110)" / connection refused

The cluster is unreachable, the port is blocked, or `DATABASE_URL` points
somewhere wrong.

```bash
nc -zv galera.its.appstate.edu 3306
mysql -h galera.its.appstate.edu -u octagon -p octagon_log -e "SELECT 1;"
```

### "Access denied for user 'octagon'@'...'"

Either the password in `DATABASE_URL` is wrong, or the grant does not cover the
host the app is connecting *from* — MySQL grants are per user *and* host, so an
app that moved to a new subnet or into containers will be denied even with the
right password. Have the DBA confirm:

```sql
SELECT user, host FROM mysql.user WHERE user = 'octagon';
SHOW GRANTS FOR 'octagon'@'%';
```

### "RSA public key is not available" on connect

MySQL 8's default `caching_sha2_password` auth needs the `cryptography`
package, which ships via the `PyMySQL[rsa]` extra in `requirements.txt`.
Reinstall dependencies if it is missing: `pip install -r requirements.txt`.

### "Incorrect string value: '\xF0\x9F...'" when saving a name or note

The database or column is `utf8` (three-byte) rather than `utf8mb4`. Check and
convert:

```sql
SELECT default_character_set_name FROM information_schema.schemata
WHERE schema_name = 'octagon_log';

ALTER DATABASE octagon_log CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE student CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### "Deadlock found when trying to get lock" (error 1213) under light load

On Galera this is usually not a local deadlock but a certification failure —
two nodes committed conflicting writes. Point `DATABASE_URL` at a single writer
node or the load balancer's single-writer VIP rather than spreading writes
across nodes.

### A migration failed halfway

MySQL commits DDL implicitly, so there is no transaction to roll back. Check
what actually landed, then fix forward:

```bash
mysql --defaults-file=/home/woodshop/.my.cnf octagon_log -e "SHOW TABLES; SELECT * FROM alembic_version;"
```

If the schema changed but `alembic_version` did not advance, either finish the
change by hand and `flask db stamp <revision>`, or restore from the pre-upgrade
backup and retry.

### "502 Bad Gateway" from Nginx

Gunicorn isn't running or is on a different port.

```bash
sudo systemctl status woodshop-log
curl http://127.0.0.1:8080     # test Gunicorn directly
```

### Database seems slow

Check connection count and long-running queries:

```bash
mysql --defaults-file=/home/woodshop/.my.cnf -e "
SELECT id, time, state, LEFT(info, 120) AS query
FROM information_schema.processlist
WHERE db = 'octagon_log' AND command != 'Sleep'
ORDER BY time DESC;
"
```

If queries are fast but requests are slow, the bottleneck is more likely the
pool than the cluster — check whether `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` is
being exhausted, and whether flow control is throttling writes:

```bash
mysql --defaults-file=/home/woodshop/.my.cnf -e "
SHOW STATUS WHERE Variable_name IN
  ('wsrep_flow_control_paused','wsrep_local_recv_queue_avg');"
```

### Need to reset everything and start fresh

> This drops production data on every node in the cluster. Take a backup first.

```bash
sudo systemctl stop woodshop-log

mysql --defaults-file=/home/woodshop/.my.cnf -e "
DROP DATABASE octagon_log;
CREATE DATABASE octagon_log CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

cd /home/woodshop/jubilant-happiness
source venv/bin/activate
export FLASK_APP=run.py
flask db upgrade
python seed_production.py
sudo systemctl start woodshop-log
```

---

## Appendix A — Running in a Container

Sections 2–9 describe the app running directly on a VM under systemd. This
appendix is the alternative: the same app in a container, for hosting that
expects an image rather than a host to configure. Sections 1 (why MySQL Galera),
3 (database setup), 11 (backups) and 13 (creating accounts) still apply — a
container changes how the app is *started*, not what it needs.

### A1. What the image does

`Dockerfile` builds on `python:3.12-slim` and starts:

```
gunicorn wsgi:app --config gunicorn.conf.py
```

`wsgi:app` is the WSGI target — the `app` object in `wsgi.py`, which is the
same entry point systemd uses in Section 9. Anything asking for a WSGI
application path (a `module:variable` string, often shown in examples as
`example.main:app`) wants exactly `wsgi:app` for this project.

Notable properties:

| | |
|---|---|
| Runs as | the unprivileged `octagon` user, not root |
| Listens on | `$PORT`, default `8080` |
| Logs to | stdout/stderr, collected by the container runtime |
| Health check | `GET /login` every 30s, via `urllib` |
| Migrations | **not** run at startup — see A4 |

### A2. Build and run

```bash
docker build -t octagon-log .
docker run --env-file .env -p 8080:8080 octagon-log
```

`.env` is the same file described in Section 6. It is excluded from the image
by `.dockerignore` and must be supplied at run time — never build secrets into
an image layer, where anyone who can pull the image can read them back.

`DATABASE_URL` must point at the MySQL Galera endpoint the container can reach.
`localhost` inside a container is the container itself, not the host, so a
database running on the Docker host is reached at `host.docker.internal` (or
the bridge gateway address) rather than `localhost`.

### A3. Tuning

All optional — the defaults match `start.sh`.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Port Gunicorn binds |
| `WORKERS` | `2` | Gunicorn worker processes |
| `GUNICORN_TIMEOUT` | `120` | Seconds before a worker is killed |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Peers whose `X-Forwarded-*` headers are trusted |
| `PROXY_HOPS` | `1` | Reverse proxies in front of the app |

`FORWARDED_ALLOW_IPS` matters more in a container than on a VM. Gunicorn
ignores `X-Forwarded-Proto` from any peer not on this list, and the default of
`127.0.0.1` is the *container's* loopback — not the reverse proxy, which
arrives as the bridge gateway or a pod address. Set it to the proxy's address
in the hosting environment.

`PROXY_HOPS` must match how many proxies actually sit in front of the app: `1`
for the single Nginx in Section 8, `2` if the hosting platform puts a load
balancer in front of that. Setting it higher than the real number lets a client
forge its own address by sending its own `X-Forwarded-For`.

### A4. Migrations

The container does not run `flask db upgrade` at startup, because two
containers starting at once would race on the same migration. Run it as a
one-off against the same image, before rolling out a release that changes the
schema:

```bash
docker run --rm --env-file .env octagon-log flask db upgrade
```

`FLASK_APP=run.py` is already set in the image, so no export is needed. The
Section 5b note about `flask db stamp head` on a pre-migration database applies
here too.

Section 5c's `seed_production.py` is interactive and runs the same way, with
`-it`:

```bash
docker run --rm -it --env-file .env octagon-log python seed_production.py
```

### A5. Reverse proxy

Section 8's Nginx config is unchanged — it still proxies to `127.0.0.1:8080`,
which is now the published container port rather than a Gunicorn process on the
host. If the hosting platform terminates TLS and proxies for you, that section
can be skipped entirely; set `FORWARDED_ALLOW_IPS` (A3) so the app sees the
original scheme.
