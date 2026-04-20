<h1 align="center">WebOnlineMonitor</h1>

<p align="center">
  Web application for monitoring users' online activity
</p>

###

<div align="center">
  <img src="https://skillicons.dev/icons?i=py" height="40" alt="python logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=html" height="40" alt="html logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=css" height="40" alt="css logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=js" height="40" alt="javascript logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=postgres" height="40" alt="postgresql logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=git" height="40" alt="git logo" />
</div>

###

## About

**WebOnlineMonitor** is a Flask-based web service for tracking and analyzing users' online activity. The application collects activity events, stores them in PostgreSQL, and provides a convenient interface for viewing statistics, filtering logs, and visualizing data.

## Features

- **Dashboard** — summary statistics for today / week / month, activity charts by hour and day of week, top users, and platform breakdown
- **Activity logs** — event table with filtering by date and users, filters are preserved between sessions
- **Timeline** — visual timeline of multiple users' activity simultaneously
- **User management** — add/remove tracked VK accounts, assign types and custom colors
- **Polling intervals** — flexible configuration of check frequency based on idle time
- **CSV export** — export events with filtering by date range and users
- **Admin panel** — manage system accounts, reset passwords, toggle admin rights

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3, Flask |
| Database | PostgreSQL + psycopg2 |
| Frontend | Jinja2, Bootstrap, Chart.js |
| Authentication | Flask session + Werkzeug |
| Timezones | pytz (Europe/Moscow) |
| WSGI | Gunicorn (wsgi.py) |

## Project Structure

```
WebOnlineMonitor/
├── app.py              # Flask application, all routes
├── wsgi.py             # Entry point for Gunicorn
├── templates/
│   ├── base.html       # Base template with navigation
│   ├── login.html      # Login page
│   ├── dashboard.html  # Main dashboard
│   ├── logs.html       # Activity log
│   ├── timeline.html   # Timeline view
│   ├── watched_users.html  # Tracked users list
│   ├── user_detail.html    # User detail page
│   ├── intervals.html      # Interval configuration
│   └── admin_users.html    # Admin panel
└── update.sh           # Service update and restart script
```

## Installation

### Requirements

- Python 3.9+
- PostgreSQL 13+

### 1. Clone the repository

```bash
git clone <repo-url>
cd WebOnlineMonitor
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask psycopg2-binary pytz werkzeug gunicorn
```

### 3. Configure the database

Edit the connection string in `app.py`:

```python
DB_DSN = "postgresql://user:password@127.0.0.1:5432/dbname"
```

### 4. Run for development

```bash
python app.py
```

### 5. Run with Gunicorn (production)

```bash
gunicorn --bind 0.0.0.0:5000 wsgi:app
```

## Deploying as a systemd service

Create `/etc/systemd/system/webmonitor.service`:

```ini
[Unit]
Description=WebOnlineMonitor Flask App
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/opt/WebOnlineMonitor
ExecStart=/opt/WebOnlineMonitor/venv/bin/gunicorn --bind 127.0.0.1:5000 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start it:

```bash
systemctl daemon-reload
systemctl enable webmonitor
systemctl start webmonitor
```

To update the application, use the `update.sh` script:

```bash
chmod +x update.sh
./update.sh
```

## Database Tables

| Table | Purpose |
|-------|---------|
| `app_users` | System accounts (login, password, role) |
| `watched_users` | Tracked VK accounts |
| `activity_events` | Activity event log |
| `platforms` | Platform reference (web, mobile, etc.) |
| `tracking_intervals` | Polling interval rules per user type |
| `user_vk_colors` | Per-user custom colors for display |

## Routes

| Route | Description |
|-------|-------------|
| `/` | Redirect to dashboard or login |
| `/login` | Login page |
| `/dashboard` | Main dashboard with statistics |
| `/logs` | Activity log with filters |
| `/timeline` | Timeline view |
| `/users` | Tracked users list |
| `/users/<vk_id>` | User detail page |
| `/intervals` | Polling interval configuration |
| `/export/csv` | Export data to CSV |
| `/admin/users` | Admin panel |
