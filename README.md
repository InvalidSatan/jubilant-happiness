# Octagon Woodshop Log

A safety logging and access-control system for the Appalachian State University Art Department's shared shop spaces. Monitors (trained student employees) use it to track who is in the shop, verify training certifications, and enforce a warning/strike system — ensuring no student works unsupervised or on equipment they haven't been trained for.

## Table of Contents

- [Problem Statement](#problem-statement)
- [Features](#features)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Usage Guide](#usage-guide)
- [Database Schema](#database-schema)
- [External Integrations](#external-integrations)
- [Configuration](#configuration)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Roadmap / Open Questions](#roadmap--open-questions)

## Problem Statement

The Art Department operates four shared shop areas — **Sculpture**, **Ceramics**, **Metal Smithing**, and **DigiLab** — containing dangerous equipment (band saws, welders, kilns, laser cutters, etc.). Students frequently use these spaces outside of regular staff hours, supervised only by trained student monitors. The department needs a way to:

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
- When a monitor ends their shift, all remaining students in that area are automatically signed out.
- Full session history with duration tracking.

### Student Sign-In / Sign-Out
- Monitor looks up a student by Banner ID.
- Before signing the student in, the system shows:
  - Equipment training status for the current area (trained / not trained per piece of equipment).
  - Active warning count.
  - Private care notes (visible to the monitor, not the student).
- The monitor must explicitly click **"Acknowledge & Sign In"** — a student cannot sign in without this step.
- Students with 3 or more active warnings are blocked from signing in entirely.

### Training & Certification Tracking
- Equipment is registered per area, with a flag indicating whether training is required.
- Student training records can be managed manually by admins (grant/revoke).
- An integration sync endpoint can pull completion data from Banner SIS and ASULearn (Moodle) when configured.

### Warning / Strike System
- Any monitor can issue a warning to a student, specifying the area and reason.
- Warnings are "active" by default; admins can resolve them.
- **3 active warnings = banned.** The system blocks sign-in and shows a clear banner on the student's profile.

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
| ORM / Database | Flask-SQLAlchemy + SQLite (default) |
| Authentication | Flask-Login (session-based) |
| Forms / CSRF | Flask-WTF |
| Frontend | Jinja2 templates + Bootstrap 5.3 (CDN) |
| Password hashing | Werkzeug (pbkdf2) |
| External API calls | Requests |

SQLite is the default database and works well for a single-department deployment. The `SQLALCHEMY_DATABASE_URI` config can be pointed at PostgreSQL or MySQL if needed.

## Getting Started

### Prerequisites

- Python 3.11 or later
- pip

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd jubilant-happiness

# Install dependencies
pip install -r requirements.txt

# Copy environment config (optional — defaults work for development)
cp .env.example .env
# Edit .env to set SECRET_KEY for production

# Seed the database with sample data
python seed.py

# Start the development server
python run.py
```

The app will be running at **http://localhost:5000**.

### Default Accounts (from seed.py)

| Username | Password | Role | Areas |
|---|---|---|---|
| `admin` | `admin` | Admin | All areas |
| `mgarcia` | `password` | Monitor | Sculpture, Ceramics |
| `jchen` | `password` | Monitor | Metal Smithing |
| `asmith` | `password` | Monitor | DigiLab |

Three sample students are also created (IDs: 900111111, 900222222, 900333333).

**Change all default passwords before deploying to production.**

## Usage Guide

### Typical Workflow

1. **Monitor logs in** with their username and password.
2. **Monitor selects an area** (e.g., "Sculpture") to begin their shift.
3. **Student arrives.** Monitor clicks "Sign In a Student" and enters the student's Banner ID.
4. **System shows the confirmation screen** with:
   - Training status for equipment in that area.
   - Any active warnings or care notes.
5. **Monitor clicks "Acknowledge & Sign In"** if everything checks out.
6. **Student finishes.** Monitor clicks "Sign Out" next to the student on the dashboard.
7. **Monitor ends their shift.** All remaining students are automatically signed out.

### Issuing a Warning

1. From the dashboard, click on a student's name to view their detail page.
2. Scroll to "Issue a Warning", select the area, enter the reason, and submit.
3. The student's active warning count updates immediately. At 3, they are banned.

### Resolving a Warning

Admins can go to **Admin > View All Warnings** and click "Resolve" on any active warning. This decreases the student's active count and may lift a ban.

## Database Schema

```
ShopArea            1──M  Equipment
   │                         │
   │                         M
   │                    student_training  ──M  Student
   │                                           │
   M                                           │
monitor_areas  ──M  Monitor                    M
                      │                     Warning
                      │                        │
                      M                        │
               MonitorSession              (issued_by → Monitor)
                                           (resolved_by → Monitor)
                      │
                      M
                 StudentVisit  ──M  Student
                    (acknowledged_by → Monitor)
```

### Key Models

| Model | Purpose |
|---|---|
| `ShopArea` | The four shop areas (Sculpture, Ceramics, Metal Smithing, DigiLab) |
| `Equipment` | A piece of equipment within an area, with a `requires_training` flag |
| `Monitor` | A student employee who can oversee shop areas; has login credentials |
| `Student` | A student who uses the shop; identified by Banner ID |
| `MonitorSession` | Tracks a monitor's on-duty shift for a specific area |
| `StudentVisit` | Tracks a student's sign-in/out, including which monitor acknowledged it |
| `Warning` | A strike issued to a student; 3 active = banned |

## External Integrations

The system includes integration stubs for two campus systems. These are located in `app/routes/integration.py`.

### Banner SIS

- **Purpose:** Pull course completion data to auto-grant equipment training certifications.
- **Status:** Stub implemented. Requires API URL and key from IT.
- **Config:** Set `BANNER_API_URL` and `BANNER_API_KEY` in `.env`.
- **Mapping:** Edit `COURSE_EQUIPMENT_MAP` in `integration.py` to map course codes (e.g., `ART 2210`) to equipment names.

### ASULearn (Moodle)

- **Purpose:** Pull module/course completion data from the LMS.
- **Status:** Stub implemented. Requires a Moodle Web Services token from IT.
- **Config:** Set `ASULEARN_API_URL` and `ASULEARN_API_TOKEN` in `.env`.
- **Mapping:** Same `COURSE_EQUIPMENT_MAP` dictionary.

### Triggering a Sync

Monitors can click **"Sync External"** on any student's detail page to pull the latest data from both systems for that student.

## Configuration

All configuration is in `config.py` and can be overridden via environment variables (or a `.env` file):

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-key-change-in-production` | Flask session secret. **Must** be changed in production. |
| `DATABASE_URL` | `sqlite:///instance/woodshop.db` | SQLAlchemy database URI. |
| `BANNER_API_URL` | *(empty)* | Banner SIS API base URL. |
| `BANNER_API_KEY` | *(empty)* | Bearer token for Banner API. |
| `ASULEARN_API_URL` | *(empty)* | ASULearn Moodle Web Services endpoint. |
| `ASULEARN_API_TOKEN` | *(empty)* | Moodle Web Services token. |

## Testing

```bash
pip install pytest
python -m pytest tests/ -v
```

The test suite covers:

- Authentication (login, logout, redirects)
- Monitor area sign-in / sign-out
- Student sign-in flow (lookup, acknowledgement, sign-in, sign-out)
- Ban enforcement (3 strikes blocks sign-in)
- Warning issuance and accumulation

Tests use an in-memory SQLite database and disable CSRF for convenience.

## Project Structure

```
.
├── app/
│   ├── __init__.py              # App factory, DB init, area seeding
│   ├── models.py                # All SQLAlchemy models
│   ├── routes/
│   │   ├── admin.py             # Admin panel (monitors, equipment, warnings)
│   │   ├── auth.py              # Login / logout
│   │   ├── integration.py       # Banner & ASULearn sync stubs
│   │   ├── monitor.py           # Monitor dashboard, sessions, student detail
│   │   └── student.py           # Student lookup, registration, sign-in/out
│   └── templates/
│       ├── base.html            # Shared layout (navbar, flash messages)
│       ├── admin/               # Admin panel templates
│       ├── auth/                # Login page
│       ├── monitor/             # Dashboard, student detail, session history
│       └── student/             # Lookup, registration, sign-in confirmation
├── tests/
│   └── test_app.py              # Smoke tests (11 tests)
├── config.py                    # App configuration
├── requirements.txt             # Python dependencies
├── run.py                       # Dev server entry point
├── seed.py                      # Sample data seeder
├── .env.example                 # Environment variable template
└── .gitignore
```

## Roadmap / Open Questions

These items came directly from the initial requirements meeting and are pending departmental decisions:

1. **Banner API access** — Need the specific endpoint URL, authentication method, and which course codes map to which equipment certifications.
2. **ASULearn integration** — Need a Moodle Web Services token and confirmation of which course/module completions to query.
3. **Strikes: global vs. per-area?** — Currently global (3 strikes in *any* area = banned from *all* areas). Can be changed to per-area if the department prefers.
4. **Student kiosk mode** — The current flow is entirely monitor-driven. If the department wants a self-service kiosk where students scan/swipe an ID, that would be an additional interface on top of the same backend.
5. **Reporting / exports** — Usage reports (hours per student, busiest times, etc.) could be added once the core logging is in production.
6. **Production deployment** — For campus deployment, consider running behind Gunicorn + Nginx with PostgreSQL instead of SQLite.
