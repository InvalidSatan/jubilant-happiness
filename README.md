# Octagon Log

A safety logging and access-control system for the Appalachian State University Art Department's shared shop spaces. Monitors (trained student employees) use it to track who is in the shop, verify training certifications, and enforce a warning/strike system — ensuring no student works unsupervised or on equipment they haven't been trained for.

## Table of Contents

- [Problem Statement](#problem-statement)
- [Who Logs In](#who-logs-in)
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

## Who Logs In

There are **two separate login systems**. They do not share a session — signing in to one does not sign you in to the other.

| Portal | URL | Who | What they do |
|---|---|---|---|
| Monitor | `/login` | Student employees | Open a shift, sign students in and out, issue warnings, run the kiosk |
| Monitor (admin) | `/login` | Shop admins | The above, plus equipment, monitor accounts, warning resolution, and reports |
| Faculty | `/faculty/login` | Faculty | Roster, training certifications, shift calendars |
| Faculty (primary admin) | `/faculty/login` | Lead faculty | The above, plus monitor accounts and other faculty accounts |

Reports live under `/admin/reports` and require an **admin monitor** account — they are not reachable from the faculty portal.

## Features

### Monitor Management
- Monitors sign in to a specific shop area to begin their shift.
- Each monitor is authorized for one or more areas by an admin or by faculty.
- When a monitor ends their shift — or simply logs out — all remaining students in that area are automatically signed out, with the sign-out monitor recorded.
- Full session history with duration tracking.

### Student Sign-In / Sign-Out
- Monitor looks up a student by Banner ID (validated as exactly 9 digits).
- Before signing the student in, the system shows:
  - Equipment training status for the current area (trained / not trained / **no record**) with semester completed.
  - Color-coded strike indicators (yellow/orange/red for 1st/2nd/3rd).
  - Private care notes (visible to the monitor, not the student).
- Per-visit notes can be added at sign-in time.
- The monitor must explicitly click **"Acknowledge & Sign In"** — a student cannot sign in without this step.
- Students with 3 or more active warnings are blocked from signing in entirely, with no override on that screen.

### Kiosk Mode
- Full-screen, dark-themed tablet interface for self-service sign-in/out.
- Students scan or type their Banner ID — the system auto-detects whether to sign in or sign out.
- Shows strike indicators and banned status with clear visual feedback.
- Auto-resets to the input screen after 4 seconds.
- Launched from the monitor dashboard; requires an active monitor session. Ending the shift stops the kiosk accepting scans.

### Faculty Portal
A separate portal at `/faculty/login` for the people who own the roster and the training data.

- **Dashboard** — counts of registered students, students with training, monitors, and areas.
- **Students** — searchable list, add individually, view and edit details (including Canvas user ID).
- **CSV upload** — bulk-register students. Requires `banner_id` (or `student_id` / `id`) and `name` (or `display_name` / `full_name` / `student_name`); `email` and `canvas_user_id` (or `canvas_id` / `canvas`) are optional. Existing Banner IDs are skipped, and per-row errors are reported without aborting the import.
- **Training** — grant, update, or revoke equipment certifications, each with the semester earned.
- **Shift calendars** — connect each area to the Google Calendar holding its monitor shift schedule (see below).
- **Monitors** and **Faculty accounts** — restricted to the primary faculty admin.

### Training & Certification Tracking
- Equipment certifications are registered per area, matching the department's actual categories:
  - **Sculpture:** Basic Woodshop, Advanced Woodshop, Welding, Casting, Carving, CNC Plasma
  - **Metal Smithing:** Torches, Machine Room, Casting Room, CNC Milling Machine, Annodizing
  - **DigiLab:** Laser, 3D Printing, Resin Printing, Shopbot, Vinyl Cutter
  - **Woodworking:** WW1, WW2, Welding, Casting, Carving
  - **Ceramics:** Kiln, Pottery Wheel, Glaze Station *(placeholders — details TBD)*
- Training records include the semester certified (e.g., "Fall 2024").
- Students with **no** training records for an area see a "No Record" badge, which is deliberately distinct from "NOT Certified" — one means nobody has assessed them here, the other means they were assessed and are not cleared.

### Warning / Strike System
- Any monitor can issue a warning to a student, specifying the area and reason.
- Warnings are "active" by default; admins can resolve them.
- **3 active warnings = banned** (global scope — across all areas).
- Color-coded strike indicators: 1st (yellow), 2nd (orange), 3rd (red).

### Monitor Shift Schedules (placeholder)
- The faculty dashboard shows upcoming monitor coverage for up to three shop areas.
- Faculty connect each area to a Google Calendar they own, from **Faculty > Shift Calendars**. The calendar ID is stored per area in the database, so no config change or restart is needed.
- Until an area is connected it shows clearly badged **Sample** data so the layout is visible; connected areas show **Live** events.
- Read-only. The app never creates or modifies anything in Google Calendar.
- **Not yet usable in production:** a Google API key can only read *public* calendars. Private shop calendars will need a service account instead — undecided.

### Reporting & Exports
- **Visit Log** — Student sign-in/out history with area, monitor, and note details.
- **Monitor Coverage** — Shift sessions with per-monitor hours summary.
- **Safety & Warnings** — Strike counts, per-area breakdown, currently banned students.
- All reports support **date range** and **area** filtering.
- One-click **CSV export** for each report.

### Admin Panel
- Create and edit monitor accounts, assign area authorizations.
- Manage equipment inventory per area.
- Grant or revoke student training certifications.
- View and resolve all warnings.
- Dashboard with real-time counts (monitors on duty, students signed in, etc.).

## Architecture

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Web framework | Flask 3.1 |
| ORM / Database | Flask-SQLAlchemy — MySQL (Galera) in production, SQLite for local dev |
| Migrations | Flask-Migrate (Alembic) |
| Authentication | Flask-Login (session-based, two user types) |
| Frontend | Jinja2 templates + Bootstrap 5.3 (CDN) |
| Password hashing | Werkzeug (pbkdf2) |
| Production server | Gunicorn |

SQLite is the default for local development and the test suite. Production runs against the departmental **MySQL Galera cluster** — set `DATABASE_URL` to a `mysql://` URI and see [DEPLOYMENT.md](DEPLOYMENT.md). No model or query in the app is database-specific, so the same code runs on both.

> **Note:** Bootstrap is loaded from the jsDelivr CDN. On a machine with no internet access, or a network that blocks the CDN, every page renders as unstyled HTML.

## Run Locally

### Prerequisites

- Python 3.11 or later
- pip

### Quick Start (Linux / macOS)

```bash
git clone <repo-url>
cd jubilant-happiness

python -m venv .venv
source .venv/bin/activate

# requirements-dev.txt includes requirements.txt plus pytest
pip install -r requirements-dev.txt

# Flask does not create this directory for you
mkdir -p instance

export FLASK_APP=run.py
flask db upgrade
python seed.py

python run.py
```

### Quick Start (Windows — Command Prompt)

```cmd
git clone <repo-url>
cd jubilant-happiness

python -m venv .venv
.venv\Scripts\activate.bat

pip install -r requirements-dev.txt

mkdir instance

set FLASK_APP=run.py
flask db upgrade
python seed.py

python run.py
```

(PowerShell: activate with `.venv\Scripts\Activate.ps1` and use `$env:FLASK_APP = "run.py"` instead of `set`.)

The app will be running at **http://localhost:5000**.

### About `.env`

**You do not need a `.env` file to run locally**, and copying `.env.example` verbatim will break the app — its `DATABASE_URL` points at the MySQL Galera cluster, which isn't running on your machine. `config.py` already defaults to a working SQLite path.

If you do create one, note that a *relative* SQLite path does not work: Flask-SQLAlchemy resolves it against the instance folder, so `sqlite:///instance/woodshop.db` is looked up at `instance/instance/woodshop.db` and fails with "unable to open database file". Use an absolute path (four slashes) or omit the setting entirely.

### Demo / Walkthrough Data

`seed.py` creates the bare minimum. For a walkthrough where dashboards and reports are populated, follow it with:

```bash
python seed_demo.py
```

This adds 5 more students, 16 training certifications across two semesters, three weeks of monitor shifts and student visits, and warnings that leave one student banned. It skips itself if the demo data is already present. **Do not run it against a production database.**

`demo_students_sample.csv` is a small valid file for exercising the faculty CSV upload screen.

### Default Accounts

From `seed.py`:

| Username | Password | Portal | Role |
|---|---|---|---|
| `admin` | `admin` | `/login` | Admin monitor — all areas |
| `mgarcia` | `password` | `/login` | Monitor — Sculpture, Ceramics |
| `jchen` | `password` | `/login` | Monitor — Metal Smithing |
| `asmith` | `password` | `/login` | Monitor — DigiLab |
| `bwilson` | `password` | `/login` | Monitor — Woodworking |
| `faculty` | `faculty` | `/faculty/login` | Faculty — primary admin |
| `instructor` | `password` | `/faculty/login` | Faculty |

Three sample students are also created (Banner IDs 900111111, 900222222, 900333333).

**Change all default passwords before any real use.**

### Resetting the Database

```bash
rm -f instance/woodshop.db
mkdir -p instance
flask db upgrade
python seed.py
```

On Windows Command Prompt, use `del instance\woodshop.db`.

### Applying New Migrations

After pulling changes that modify the schema:

```bash
flask db upgrade
```

**If you have an existing pre-migration database** (created before `migrations/` was added), Alembic doesn't know what version it's at. Stamp it once, then future upgrades work normally:

```bash
flask db stamp head
```

If your database is missing columns the current code expects (e.g. `shop_area.calendar_id` or `student.canvas_user_id`), the cleanest fix is to delete `instance/woodshop.db` and rebuild from scratch.

## Deploy to a Server

The short version is below. [DEPLOYMENT.md](DEPLOYMENT.md) covers the full MySQL Galera production setup.

### 1. Install and Configure

```bash
git clone <repo-url>
cd jubilant-happiness

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt   # no test tooling in production

cp .env.example .env
```

Edit `.env` and set at minimum:

```bash
# REQUIRED — generate a random secret key:
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<paste-your-generated-key-here>

# Point at the MySQL Galera cluster, or comment out for SQLite.
# `mysql://` is rewritten to `mysql+pymysql://` automatically.
DATABASE_URL=mysql://octagon:password@galera.its.appstate.edu:3306/octagon_log

PORT=8080
WORKERS=2
```

### 2. Build and Seed the Database

```bash
mkdir -p instance
export FLASK_APP=run.py
flask db upgrade
python seed_production.py
```

`seed_production.py` creates the equipment for each area and then **prompts you interactively** to set a username and password for the primary faculty admin and the admin monitor. Unlike `seed.py`, it creates no sample students or test monitors, and no default passwords. Run it on a terminal you can type into — it will block waiting for input.

### 3. Start the Server

```bash
chmod +x start.sh
./start.sh
```

This runs gunicorn on `0.0.0.0:8080` with 2 workers. Use `./start.sh --dev` for the Flask debug server instead.

### Or: run it in a container

For hosting that expects an image rather than a host to configure:

```bash
docker build -t octagon-log .
docker run --env-file .env -p 8080:8080 octagon-log
```

Same app, same `.env`, same WSGI entry point — the image runs `gunicorn wsgi:app`. Migrations are not run at startup; apply them as a one-off with `docker run --rm --env-file .env octagon-log flask db upgrade`. [Appendix A of DEPLOYMENT.md](DEPLOYMENT.md#appendix-a--running-in-a-container) covers the details.

### 4. Run Behind a Reverse Proxy (Recommended)

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
Description=Octagon Log
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

```bash
sudo systemctl daemon-reload
sudo systemctl enable woodshop-log
sudo systemctl start woodshop-log
sudo systemctl status woodshop-log
```

### 6. Backups

The SQLite database lives at `instance/woodshop.db`:

```bash
0 2 * * * cp /path/to/jubilant-happiness/instance/woodshop.db /path/to/backups/woodshop-$(date +\%Y\%m\%d).db
```

For MySQL backups, see [DEPLOYMENT.md](DEPLOYMENT.md) — note that the Galera cluster is backed up by ITS at the cluster level.

## Usage Guide

### Typical Monitor Workflow

1. **Monitor logs in** at `/login`.
2. **Monitor selects an area** (e.g., "Sculpture") to begin their shift.
3. **Student arrives.** Monitor clicks "Sign In a Student" and enters the student's Banner ID.
4. **System shows the confirmation screen** with training status, strikes, and care notes.
5. **Monitor clicks "Acknowledge & Sign In"** if everything checks out.
6. **Student finishes.** Monitor clicks "Sign Out" next to the student on the dashboard.
7. **Monitor ends their shift.** All remaining students are automatically signed out.

### Typical Faculty Workflow

1. **Faculty logs in** at `/faculty/login`.
2. At the start of term, **upload the roster** via CSV, or add students individually.
3. As students complete safety training, **grant certifications** with the semester earned.
4. Optionally, **connect each area's shift calendar** under Shift Calendars.

### Kiosk Mode

1. Monitor signs into an area and clicks **"Launch Kiosk"** on the dashboard.
2. Students type or scan their Banner ID — sign-in vs. sign-out is auto-detected.
3. After 4 seconds the screen resets for the next student.
4. Click **"Exit Kiosk"** to return to the dashboard.

### Issuing and Resolving a Warning

1. From the dashboard, click a student's name to open their detail page.
2. Scroll to "Issue a Warning", select the area, enter the reason, and submit.
3. At 3 active warnings the student is banned.
4. Admins resolve warnings under **Admin > View All Warnings**, which may lift a ban.

### Viewing Reports

Admin monitors click **Reports** in the navbar (`/admin/reports`) for the visit log, monitor coverage, and safety reports — each filterable by area and date range, each exportable to CSV.

## Database Schema

```
ShopArea            1──M  Equipment
   │ (calendar_id)            │
   │                          M
   │                     student_training  ──M  Student
   │                     (certified_semester,       │
   │                      source)                   │
   M                                                M
monitor_areas  ──M  Monitor                      Warning
                      │                             │
                      M                    (issued_by → Monitor)
               MonitorSession              (resolved_by → Monitor)
                      │
                      M
                 StudentVisit  ──M  Student
                    (acknowledged_by → Monitor)
                    (signed_out_by → Monitor)
                    (note)

Faculty  (separate login; no foreign keys into the logging tables)
```

### Key Models

| Model | Purpose |
|---|---|
| `ShopArea` | Five shop areas; also holds the Google Calendar id for its shift schedule |
| `Equipment` | A certification category within an area, with a `requires_training` flag |
| `Monitor` | A student employee who oversees shop areas; has login credentials |
| `Faculty` | A faculty member who manages the roster and training; separate login |
| `Student` | A student who uses the shop; identified by Banner ID |
| `MonitorSession` | Tracks a monitor's on-duty shift for a specific area |
| `StudentVisit` | Tracks a student's sign-in/out, which monitors handled it, and visit notes |
| `Warning` | A strike issued to a student; 3 active = banned |

## External Integrations

Integration code lives in `app/routes/integration.py`. All of it is stubbed — the plumbing is written so that setting credentials is the only step needed, but none of it is live.

| Integration | Purpose | Status |
|---|---|---|
| **Banner SIS** | Pull course completions to auto-grant certifications | Stub. Needs API URL and key from IT. |
| **ASULearn (Moodle)** | Pull module/course completions from the LMS | Stub. Deferred until the LMS transition settles. |
| **Canvas LMS** | Pull course enrollments, correlated via `Student.canvas_user_id` | Stub. Needs an API token. |
| **Google Calendar** | Read monitor shift schedules per area | Placeholder. Needs an API key; see caveat below. |

Banner, ASULearn, and Canvas all return an empty list when unconfigured, so nothing breaks. Monitors can click **"Sync External"** on a student's detail page to pull from all three at once; with nothing configured it reports that no new training data was found.

`COURSE_EQUIPMENT_MAP` in `integration.py` maps external course identifiers to equipment names and is currently empty — fill it in as the department finalizes which courses grant which certifications.

**Google Calendar differs deliberately:** when an area has no calendar connected it returns clearly-labelled sample shifts rather than nothing, so the dashboard shows the intended layout. Sample events are flagged and badged in the UI. Note that an API key can only read **public** calendars — private shop calendars will require a service account instead.

## Configuration

All configuration is in `config.py` and can be overridden via environment variables (or a `.env` file).

Every value below is read with `os.getenv()` at import time, and no secret has a committed default — `SECRET_KEY` falls back to an obvious dev placeholder that the production config refuses to start without, and every credential defaults to empty. A containerized deployment can therefore skip `.env` entirely and inject these as environment variables.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-key-change-in-production` | Flask session secret. **Must** be set in production. |
| `DATABASE_URL` | absolute path to `instance/woodshop.db` | SQLAlchemy database URI. A `mysql://` scheme is rewritten to `mysql+pymysql://` and defaulted to `charset=utf8mb4`. |
| `PORT` | `8080` | Server port (used by `start.sh`). |
| `WORKERS` | `2` | Gunicorn worker count (used by `start.sh`). |
| `DB_POOL_SIZE` | `5` | MySQL pool size, per process (production config only). |
| `DB_MAX_OVERFLOW` | `10` | MySQL pool overflow (production config only). |
| `DB_POOL_TIMEOUT` | `30` | MySQL pool timeout (production config only). |
| `DB_POOL_RECYCLE` | `1800` | Connection recycle seconds; keep below the cluster's `wait_timeout` (production config only). |
| `BANNER_API_URL` | *(empty)* | Banner SIS API base URL. |
| `BANNER_API_KEY` | *(empty)* | Bearer token for Banner API. |
| `ASULEARN_API_URL` | *(empty)* | ASULearn Moodle Web Services endpoint. |
| `ASULEARN_API_TOKEN` | *(empty)* | Moodle Web Services token. |
| `CANVAS_API_URL` | *(empty)* | Canvas API base URL. |
| `CANVAS_API_TOKEN` | *(empty)* | Canvas API token. |
| `GOOGLE_CALENDAR_API_URL` | Google's v3 endpoint | Calendar API base URL. |
| `GOOGLE_CALENDAR_API_KEY` | *(empty)* | Calendar API key. |
| `GOOGLE_CALENDAR_CARD_COUNT` | `3` | How many area schedule cards the faculty dashboard shows. |

Which calendar backs each area is **not** configured here — faculty set it per area in the portal, and it is stored on `ShopArea.calendar_id`.

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

The suite is **81 tests** covering:

- Authentication for both portals (login, logout, redirects, access control)
- Banner ID validation
- Monitor area sign-in / sign-out
- Student sign-in flow (lookup, acknowledgement, sign-in, sign-out)
- Ban enforcement (3 strikes blocks sign-in)
- Warning issuance and accumulation
- Kiosk mode (scan sign-in, auto sign-out, unknown/banned students)
- Reports (admin access control, all 3 reports, CSV exports, filters)
- Faculty portal (students, CSV upload, training grant/update/revoke, monitors, faculty accounts)
- Shift calendars (connect, disconnect, malformed ID rejection, sample-data labelling)

Tests use an in-memory SQLite database and disable CSRF. They need neither a built database nor the `instance` directory, so they can be run immediately after installing dependencies.

## Project Structure

```
.
├── app/
│   ├── __init__.py              # App factory, DB init, Jinja filters
│   ├── models.py                # All SQLAlchemy models
│   ├── utils.py                 # Banner ID validation, shift time formatting
│   ├── routes/
│   │   ├── admin.py             # Admin panel (monitors, equipment, warnings)
│   │   ├── auth.py              # Monitor login / logout
│   │   ├── faculty.py           # Faculty portal (roster, training, calendars)
│   │   ├── integration.py       # Banner, ASULearn, Canvas, Google Calendar
│   │   ├── kiosk.py             # Kiosk mode (tablet self-service UI)
│   │   ├── monitor.py           # Monitor dashboard, sessions, student detail
│   │   ├── reports.py           # Reporting (visits, coverage, safety) + CSV
│   │   └── student.py           # Student lookup, registration, sign-in/out
│   └── templates/
│       ├── base.html            # Shared layout (navbar, flash messages, strike CSS)
│       ├── admin/               # Admin panel templates
│       │   └── reports/         # Report hub, visits, coverage, safety
│       ├── auth/                # Monitor login page
│       ├── faculty/             # Faculty portal templates, incl. calendars.html
│       ├── kiosk/               # Full-screen kiosk interface
│       ├── monitor/             # Dashboard, student detail, session history
│       └── student/             # Lookup, registration, sign-in confirmation
├── migrations/                  # Alembic migrations (0001 schema, 0002 calendar_id)
├── tests/
│   └── test_app.py              # 81 tests
├── config.py                    # App configuration (dev + production)
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Runtime + pytest
├── run.py                       # Dev server entry point
├── wsgi.py                      # Production entry point (gunicorn)
├── start.sh                     # Deployment launcher script
├── Dockerfile                   # Container image (gunicorn wsgi:app)
├── gunicorn.conf.py             # Gunicorn settings used by the container
├── .dockerignore                # Keeps .env, venvs and local DBs out of the image
├── seed.py                      # Baseline accounts, equipment, sample students
├── seed_demo.py                 # Realistic demo history for walkthroughs
├── seed_production.py           # Equipment + interactively-created real admins
├── demo_students_sample.csv     # Sample file for the faculty CSV upload
├── DEPLOYMENT.md                # Full MySQL Galera production deployment guide
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
- Faculty portal with roster management and CSV student upload
- Production deployment support (gunicorn, MySQL Galera, startup script)
- Database migrations

### In Progress
- **Google Calendar shift schedules** — placeholder cards and faculty-managed calendar IDs are in. Blocked on deciding between public calendars and a service account, since an API key cannot read private ones.

### Deferred
- **Historical training import** — student rosters upload by CSV; existing spreadsheet *training records* would still be re-entered by hand.
- **Banner SIS integration** — waiting on API access from IT.
- **ASULearn/LMS integration** — deferred until the new LMS is adopted.
- **Ceramics certification categories** — currently placeholders, pending confirmation from ceramics faculty.

### Known Gaps
- No password reset; an admin changes passwords by hand.
- No notification when a student reaches three strikes — someone has to check Reports.
- No CSRF protection is registered app-wide, despite Flask-WTF being installed.
- Bootstrap loads from a CDN, so the UI is unstyled without internet access.
