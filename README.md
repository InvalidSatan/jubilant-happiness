# Octagon Woodshop Log

A safety logging and access-control system for the Appalachian State University Art Department's shared shop spaces. Monitors (trained student employees) use it to track who is in the shop, verify training certifications, and enforce a warning/strike system — ensuring no student works unsupervised or on equipment they haven't been trained for.

## Table of Contents

- [Problem Statement](#problem-statement)
- [Features](#features)
- [Architecture](#architecture)
- [Run Locally](#run-locally)
- [Deploy to a Server](#deploy-to-a-server)
- [Usage Guide](#usage-guide)
- [Database Schema](#database-schema)
- [External Integrations](#external-integrations)
- [Configuration](#configuration)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)

## Problem Statement

The Art Department operates five shared shop areas — **Sculpture**, **Ceramics**, **Metal Smithing**, **DigiLab**, and **Woodworking** — containing dangerous equipment (band saws, welders, kilns, laser cutters, etc.). Students frequently use these spaces outside of regular staff hours, supervised only by trained student monitors. The department needs a way to:

1. **Log** when monitors are on duty and which area they are covering.
2. **Log** when students enter and leave each area.
3. **Verify** that a student has completed the required training before using specific equipment.
4. **Flag** students who need extra attention (private care notes visible only to monitors).
5. **Enforce** a three-strike warning system — a student with three active warnings is automatically blocked from signing in.
6. **Require** a monitor to explicitly acknowledge every student sign-in (no unsupervised access).

## Features

### Monitor Management
- Monitors sign in to a specific shop area to begin their shift.
- Each monitor is authorized for one or more areas by an admin.
- When a monitor ends their shift, all remaining students in that area are automatically signed out (with the sign-out monitor recorded).
- Full session history with duration tracking.

### Student Sign-In / Sign-Out
- Monitor looks up a student by Banner ID.
- Before signing the student in, the system shows:
  - Equipment training status for the current area (trained / not trained / **no record**) with semester completed.
  - Color-coded strike indicators (yellow/orange/red for 1st/2nd/3rd).
  - Private care notes (visible to the monitor, not the student).
- Per-visit notes can be added at sign-in time.
- The monitor must explicitly click **"Acknowledge & Sign In"** — a student cannot sign in without this step.
- Students with 3 or more active warnings are blocked from signing in entirely.

### Kiosk Mode
- Full-screen, dark-themed tablet interface for self-service sign-in/out.
- Students scan or type their Banner ID — the system auto-detects whether to sign in or sign out.
- Shows strike indicators and banned status with clear visual feedback.
- Auto-resets to the input screen after 4 seconds.
- Launched from the monitor dashboard; requires an active monitor session.

### Training & Certification Tracking
- Equipment certifications are registered per area, matching the department's actual categories:
  - **Sculpture:** Basic Woodshop, Advanced Woodshop, Welding, Casting, Carving, CNC Plasma
  - **Metal Smithing:** Torches, Machine Room, Casting Room, CNC Milling Machine, Annodizing
  - **DigiLab:** Laser, 3D Printing, Resin Printing, Shopbot, Vinyl Cutter
  - **Woodworking:** WW1, WW2, Welding, Casting, Carving
  - **Ceramics:** Kiln, Pottery Wheel, Glaze Station *(placeholders — details TBD)*
- Training records include the semester certified (e.g., "Fall 2024").
- Student training records can be managed manually by admins (grant/revoke).
- Students with no training records for an area see a "No Record" badge (distinct from "NOT Certified").

### Warning / Strike System
- Any monitor can issue a warning to a student, specifying the area and reason.
- Warnings are "active" by default; admins can resolve them.
- **3 active warnings = banned** (global scope — across all areas).
- Color-coded strike indicators: 1st (yellow), 2nd (orange), 3rd (red).

### Reporting & Exports
- **Visit Log** — Student sign-in/out history with area, monitor, and note details.
- **Monitor Coverage** — Shift sessions with per-monitor hours summary.
- **Safety & Warnings** — Strike counts, per-area breakdown, currently banned students.
- All reports support **date range** and **area** filtering.
- One-click **CSV export** for each report.

### Admin Panel
- Create and edit monitor accounts, assign area authorizations.
- Manage equipment inventory per area (add, edit, delete — deletion is blocked
  while training records reference the item).
- Grant or revoke student training certifications (with semester).
- View and resolve all warnings.
- Dashboard with real-time counts (monitors on duty, students signed in, etc.).
- **External Integrations** status panel and a one-click **Sync All Students**.

> Every signed-in user (monitor or faculty) can change their own password via
> the **Account** link in the navbar — change the seed passwords on first login.

## Architecture

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Web framework | Flask 3.1 |
| ORM / Database | Flask-SQLAlchemy + SQLite (default) |
| Authentication | Flask-Login (session-based) |
| Forms / CSRF | Flask-WTF |
| Frontend | Jinja2 templates + Bootstrap 5.3 (CDN) |
| Password hashing | Werkzeug (pbkdf2) |
| Production server | Gunicorn |

SQLite is the default database and works well for a single-department deployment. The `DATABASE_URL` config can be pointed at PostgreSQL or MySQL if needed.

## Run Locally

### Prerequisites

- Python 3.11 or later
- pip

### Quick Start (Linux / macOS)

```bash
# Clone the repository
git clone <repo-url>
cd jubilant-happiness

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create the SQLite instance dir, copy the env template
mkdir -p instance
cp .env.example .env
# Edit .env as needed (dev default SECRET_KEY works fine)

# Apply migrations to create the schema, then seed demo data
export FLASK_APP=run.py
flask db upgrade
python seed.py

# Start the development server
python run.py
```

### Quick Start (Windows — Command Prompt)

```cmd
git clone <repo-url>
cd jubilant-happiness

python -m venv .venv
.venv\Scripts\activate.bat

pip install -r requirements.txt

mkdir instance
copy .env.example .env
rem Edit .env in Notepad: `notepad .env`

set FLASK_APP=run.py
flask db upgrade
python seed.py

python run.py
```

(PowerShell: activate with `.venv\Scripts\Activate.ps1` and use `$env:FLASK_APP = "run.py"` instead of `set`.)

The app will be running at **http://localhost:5000** (or the `PORT` you set in `.env`).

### Default Accounts (from seed.py)

| Username | Password | Role | Areas |
|---|---|---|---|
| `admin` | `admin` | Admin | All areas |
| `mgarcia` | `password` | Monitor | Sculpture, Ceramics |
| `jchen` | `password` | Monitor | Metal Smithing |
| `asmith` | `password` | Monitor | DigiLab |
| `bwilson` | `password` | Monitor | Woodworking |

Three sample students are also created (IDs: 900111111, 900222222, 900333333).

### Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

All tests should pass. The test suite uses an in-memory SQLite database (bypassing migrations via `db.create_all()` in TESTING mode) and disables CSRF.

### Resetting the Database

```bash
rm -f instance/woodshop.db
mkdir -p instance
flask db upgrade
python seed.py
```

On Windows Command Prompt:

```cmd
del instance\woodshop.db
flask db upgrade
python seed.py
```

### Applying New Migrations

After pulling changes that modify the schema, run:

```bash
flask db upgrade
```

**If you have an existing pre-migration database** (created before `migrations/` was added to the repo), Alembic doesn't know what version it's at. Stamp it as up-to-date once, then future upgrades will work normally:

```bash
flask db stamp head
```

If your existing database is missing columns that the current code expects (e.g. `student.canvas_user_id`), the cleanest fix is to delete `instance/woodshop.db` and run `flask db upgrade && python seed.py` from scratch.

## Deploy to a Server

This section covers deploying the app as a **beta/test instance** on a Linux server.

### 1. Install and Configure

```bash
# Clone and enter the repo
git clone <repo-url>
cd jubilant-happiness

# Create a virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies (includes gunicorn)
pip install -r requirements.txt

# Copy the environment template and configure it
cp .env.example .env
```

Edit `.env` and set at minimum:

```bash
# REQUIRED — generate a random secret key:
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<paste-your-generated-key-here>

# Optional — change port or worker count
PORT=8080
WORKERS=2
```

### 2. Seed the Database

```bash
mkdir -p instance
python seed.py
```

**Change all default passwords** via the Admin panel after first login.

### 3. Start the Server

```bash
chmod +x start.sh
./start.sh
```

This runs gunicorn on `0.0.0.0:8080` with 2 workers, access logs to stdout. The app is now accessible at `http://<server-ip>:8080`.

For development mode (Flask debug server) instead:

```bash
./start.sh --dev
```

### 4. Run Behind a Reverse Proxy (Recommended)

For HTTPS and a clean URL, put Nginx in front of gunicorn. Example Nginx config:

```nginx
server {
    listen 80;
    server_name shoplog.art.appstate.edu;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name shoplog.art.appstate.edu;

    ssl_certificate     /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 5. Keep It Running (systemd)

Create `/etc/systemd/system/woodshop-log.service`:

```ini
[Unit]
Description=Octagon Woodshop Log
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/jubilant-happiness
EnvironmentFile=/path/to/jubilant-happiness/.env
ExecStart=/path/to/jubilant-happiness/venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8080 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable woodshop-log
sudo systemctl start woodshop-log
sudo systemctl status woodshop-log    # verify it's running
```

### 6. Backups

The SQLite database lives at `instance/woodshop.db`. Back it up regularly:

```bash
# Simple cron job (e.g., nightly at 2 AM)
0 2 * * * cp /path/to/jubilant-happiness/instance/woodshop.db /path/to/backups/woodshop-$(date +\%Y\%m\%d).db
```

## Usage Guide

### Typical Workflow

1. **Monitor logs in** with their username and password.
2. **Monitor selects an area** (e.g., "Sculpture") to begin their shift.
3. **Student arrives.** Monitor clicks "Sign In a Student" and enters the student's Banner ID.
4. **System shows the confirmation screen** with:
   - Training status (with semester) for equipment in that area.
   - Any active warnings (color-coded) or care notes.
5. **Monitor clicks "Acknowledge & Sign In"** if everything checks out.
6. **Student finishes.** Monitor clicks "Sign Out" next to the student on the dashboard.
7. **Monitor ends their shift.** All remaining students are automatically signed out.

### Kiosk Mode

1. Monitor signs into an area and clicks **"Launch Kiosk"** on the dashboard.
2. The tablet displays a full-screen dark-themed interface.
3. Students type or scan their Banner ID — the system auto-detects sign-in vs. sign-out.
4. After 4 seconds the screen resets for the next student.
5. Click **"Exit Kiosk"** to return to the dashboard.

### Issuing a Warning

1. From the dashboard, click on a student's name to view their detail page.
2. Scroll to "Issue a Warning", select the area, enter the reason, and submit.
3. The student's active warning count updates immediately. At 3, they are banned.

### Resolving a Warning

Admins can go to **Admin > View All Warnings** and click "Resolve" on any active warning. This decreases the student's active count and may lift a ban.

### Viewing Reports

Admins can click **Reports** in the navbar to access:
- **Visit Log** — filter by area and date range, export to CSV.
- **Monitor Coverage** — see shift hours per monitor, export to CSV.
- **Safety & Warnings** — review strikes by area, see banned students, export to CSV.

## Database Schema

```
ShopArea            1──M  Equipment
   │                         │
   │                         M
   │                    student_training  ──M  Student
   │                    (certified_semester,       │
   │                     source)                   │
   M                                               M
monitor_areas  ──M  Monitor                     Warning
                      │                            │
                      M                   (issued_by → Monitor)
               MonitorSession             (resolved_by → Monitor)
                      │
                      M
                 StudentVisit  ──M  Student
                    (acknowledged_by → Monitor)
                    (signed_out_by → Monitor)
                    (note)
```

### Key Models

| Model | Purpose |
|---|---|
| `ShopArea` | Five shop areas (Sculpture, Ceramics, Metal Smithing, DigiLab, Woodworking) |
| `Equipment` | A certification category within an area, with a `requires_training` flag |
| `Monitor` | A student employee who can oversee shop areas; has login credentials |
| `Student` | A student who uses the shop; identified by Banner ID |
| `MonitorSession` | Tracks a monitor's on-duty shift for a specific area |
| `StudentVisit` | Tracks a student's sign-in/out, which monitors handled it, and visit notes |
| `Warning` | A strike issued to a student; 3 active = banned |

## External Integrations

The system includes integration stubs for three campus systems (Banner SIS,
ASULearn/Moodle, and Canvas LMS). These are located in
`app/routes/integration.py`. The admin dashboard shows a **External
Integrations** panel indicating which ones currently have credentials
configured.

### Banner SIS

- **Purpose:** Pull course completion data to auto-grant equipment training certifications.
- **Status:** Stub implemented. Requires API URL and key from IT.
- **Config:** Set `BANNER_API_URL` and `BANNER_API_KEY` in `.env`.
- **Mapping:** Edit `COURSE_EQUIPMENT_MAP` in `integration.py` to map course codes (e.g., `ART 2210`) to equipment names.

### ASULearn (Moodle)

- **Purpose:** Pull module/course completion data from the LMS.
- **Status:** Stub implemented. Deferred until new LMS is adopted (summer transition).
- **Config:** Set `ASULEARN_API_URL` and `ASULEARN_API_TOKEN` in `.env`.

### Canvas LMS

- **Purpose:** Pull a student's active course enrollments to auto-grant
  equipment training certifications.
- **Status:** Stub implemented (`fetch_canvas_enrollments`). Requires a Canvas
  API token and confirmation of the course-code convention (`course_code` vs.
  SIS id).
- **Config:** Set `CANVAS_API_URL` (e.g. `https://appstate.instructure.com/api/v1`)
  and `CANVAS_API_TOKEN` in `.env`. Generate the token under
  *Canvas > Account > Settings > Approved Integrations*.
- **Linking students:** Set each student's numeric **Canvas User ID** (faculty
  student detail page, the add-student form, or the `canvas_user_id` CSV
  column). The sync uses this to correlate Canvas enrollments back to the
  local student.
- **Mapping:** Set `COURSE_EQUIPMENT_MAP_JSON` (a JSON object) in the
  environment to map Canvas `course_code` **or** `sis_course_id` values to
  equipment names — no code edit required. Until it is populated, syncing
  succeeds but grants nothing. The in-code `COURSE_EQUIPMENT_MAP` in
  `integration.py` serves as a documented default/fallback.
- **Pagination:** `fetch_canvas_enrollments` follows Canvas `Link` headers, so
  students with more than one page of courses are handled correctly.

### Triggering a Sync

- **One student:** Monitors click **"Sync External"** on a student's detail
  page.
- **Whole roster:** Admins click **"Sync All Students"** on the admin
  dashboard's *External Integrations* panel — this syncs every student that has
  a Canvas user id or email. Run it after linking a Canvas class.

Synced certifications are tagged with their origin (`banner` / `asulearn` /
`canvas`) rather than `manual`, so faculty can distinguish auto-granted training
on the student detail page.

## Configuration

All configuration is in `config.py` and can be overridden via environment variables (or a `.env` file):

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-key-change-in-production` | Flask session secret. **Must** be set in production. |
| `DATABASE_URL` | `sqlite:///instance/woodshop.db` | SQLAlchemy database URI. |
| `DISPLAY_TIMEZONE` | `America/New_York` | IANA timezone for displaying timestamps (stored in UTC). |
| `PORT` | `8080` | Server port (used by `start.sh`). |
| `WORKERS` | `2` | Gunicorn worker count (used by `start.sh`). |
| `BANNER_API_URL` | *(empty)* | Banner SIS API base URL. |
| `BANNER_API_KEY` | *(empty)* | Bearer token for Banner API. |
| `ASULEARN_API_URL` | *(empty)* | ASULearn Moodle Web Services endpoint. |
| `ASULEARN_API_TOKEN` | *(empty)* | Moodle Web Services token. |
| `CANVAS_API_URL` | *(empty)* | Canvas API base URL (e.g. `https://appstate.instructure.com/api/v1`). |
| `CANVAS_API_TOKEN` | *(empty)* | Canvas API access token. |
| `COURSE_EQUIPMENT_MAP_JSON` | *(empty)* | JSON mapping of course identifiers → equipment names for auto-granting training. |

### Security notes

- **CSRF protection** is enabled globally (Flask-WTF `CSRFProtect`); every form
  POST carries a token. The test suite disables it via `WTF_CSRF_ENABLED = False`.
- In **production** (`ProductionConfig`), the session cookie is marked
  `Secure` + `HttpOnly` + `SameSite=Lax`, and `ProxyFix` is applied so the app
  honors the reverse proxy's `X-Forwarded-*` headers. If you later embed the
  tool inside a Canvas iframe, you will need `SESSION_COOKIE_SAMESITE = "None"`
  (which requires HTTPS) so the session cookie survives the third-party frame.

## Testing

```bash
pip install pytest
python -m pytest tests/ -v
```

The test suite (107 tests) covers:

- Authentication (login, logout, redirects)
- Monitor area sign-in / sign-out
- Student sign-in flow (lookup, acknowledgement, sign-in, sign-out)
- Ban enforcement (3 strikes blocks sign-in)
- Warning issuance and accumulation
- Kiosk mode (scan sign-in, auto sign-out, unknown/banned students)
- Reports (admin access control, all 3 reports, CSV exports, filters)
- Faculty portal (auth, student management, CSV upload, training, monitors)
- Security (CSRF enforcement, open-redirect prevention, faculty/monitor
  cross-role isolation, Banner ID validation)
- External training sync (course→equipment mapping, Canvas source tagging,
  pagination, bulk "sync all")
- Local-timezone display conversion and the issue-warning area list

Most tests use an in-memory SQLite database and disable CSRF for convenience;
`tests/test_security.py` runs a dedicated set with CSRF **enabled** to confirm
the protection is active.

## Project Structure

```
.
├── app/
│   ├── __init__.py              # App factory, DB init, area seeding
│   ├── models.py                # All SQLAlchemy models
│   ├── routes/
│   │   ├── __init__.py          # Shared route helpers (safe redirect, faculty guard)
│   │   ├── admin.py             # Admin panel (monitors, equipment, warnings)
│   │   ├── auth.py              # Login / logout
│   │   ├── faculty.py           # Faculty portal (students, training, CSV, monitors)
│   │   ├── integration.py       # Banner / ASULearn / Canvas sync stubs
│   │   ├── kiosk.py             # Kiosk mode (tablet self-service UI)
│   │   ├── monitor.py           # Monitor dashboard, sessions, student detail
│   │   ├── reports.py           # Reporting (visits, coverage, safety) + CSV export
│   │   └── student.py           # Student lookup, registration, sign-in/out
│   └── templates/
│       ├── base.html            # Shared layout (navbar, flash messages, strike CSS)
│       ├── admin/               # Admin panel templates
│       │   └── reports/         # Report hub, visits, coverage, safety templates
│       ├── auth/                # Login page
│       ├── faculty/             # Faculty portal templates
│       ├── kiosk/               # Full-screen kiosk interface
│       ├── monitor/             # Dashboard, student detail, session history
│       └── student/             # Lookup, registration, sign-in confirmation
├── tests/
│   ├── test_app.py              # Functional tests (auth, sessions, kiosk, reports, faculty)
│   ├── test_security.py         # CSRF, open-redirect, cross-role isolation
│   ├── test_integration_sync.py # Banner/ASULearn/Canvas training sync
│   ├── test_display.py          # Local-timezone formatting, warning area list
│   ├── test_account.py          # Self-service password change
│   └── test_equipment.py        # Admin equipment edit/delete
├── config.py                    # App configuration (dev + production)
├── requirements.txt             # Python dependencies
├── run.py                       # Dev server entry point
├── wsgi.py                      # Production entry point (gunicorn)
├── start.sh                     # Deployment launcher script
├── seed.py                      # Sample data seeder
├── .env.example                 # Environment variable template
└── .gitignore
```

## Roadmap

### Completed
- Core logging system (monitor sessions, student visits, sign-in/out)
- Real certification categories matching department spreadsheets
- Semester tracking on training records
- Per-visit notes and sign-out monitor tracking
- Color-coded 3-strike warning system (global scope)
- "No Record" vs "NOT Certified" distinction
- Kiosk mode for tablet self-service
- Reporting with CSV export (visits, coverage, safety)
- Production deployment support (gunicorn, startup script)

### Deferred
- **CSV spreadsheet import** — Tool to bulk-import existing spreadsheet data. May not be needed.
- **Banner SIS integration** — Auto-sync training certifications from course completions. Waiting on API access from IT.
- **ASULearn/LMS integration** — Deferred until new LMS is adopted (summer transition).
