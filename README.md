
# SmartRoute-Sullia

A Django-based transit routing app for Sullia that helps users visualize bus stops and routes, compute shortest paths, and access route statistics via a REST API. Built for commuters, operators, and developers who need a simple, local-first routing tool.

## Features
- **Map UI at `/`** to visualize stops and routes
- **REST APIs** for stops, routes, shortest path, and stats
- **Seed data** via Django fixtures for quick start
- **Env-configurable** settings and optional OpenRouteService integration
- **Static files** served via WhiteNoise for easy deployment

## Tech Stack
- Django 5.2, Django REST Framework
- SQLite (development)
- Python 3.10+

## Getting Started

### Prerequisites
- Python 3.10+
- Git
- Optional: `virtualenv`

### Setup (Windows PowerShell)
```powershell
# 1) Clone
git clone <your-repo-url>
cd "SmartRoute Sullia"

# 2) Create and activate venv
python -m venv .venv
 .\.venv\Scripts\activate

# 3) Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4) Create .env in repo root
@'
SECRET_KEY=replace-with-a-secure-random-string
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
OPENROUTESERVICE_API_KEY=
CSRF_TRUSTED_ORIGINS=
'@ | Out-File -Encoding UTF8 .env

# 5) Migrate database
python manage.py migrate

# 6) (Optional) Load seed data
python manage.py loaddata transit/fixtures/initial_data.json

# 7) Run server
python manage.py runserver
```

Then open http://127.0.0.1:8000/

## Environment Variables
- `SECRET_KEY` (required): Django secret key.
- `DEBUG` (bool): `True` for local development.
- `ALLOWED_HOSTS` (CSV): e.g., `127.0.0.1,localhost`.
- `OPENROUTESERVICE_API_KEY` (optional): Enables real road distances/routes.
- `CSRF_TRUSTED_ORIGINS` (CSV): e.g., `https://your-domain.com`.

## API Reference

Base URL: `http://127.0.0.1:8000`

- **GET `/api/stops/`**
  Returns list of bus stops.

- **POST `/api/shortest-route/`**
  Computes shortest route between points.
  Example JSON body (adjust to your schema):
  ```json
  {
    "origin_stop_id": 1,
    "destination_stop_id": 42
  }
  ```

- **GET `/api/routes/`**
  Returns available routes.

- **GET `/api/stats/`**
  Returns statistics summary.

## Project Structure
```
smartroute/          # Django project settings/urls
transit/             # App: models, views, serializers, urls, management, fixtures
templates/transit/   # Templates for frontend
manage.py            # Django CLI entrypoint
requirements.txt     # Python dependencies
```

## Static Files
WhiteNoise is enabled. For production:
```bash
python manage.py collectstatic --noinput
```

## Running Tests
```powershell
 .\.venv\Scripts\activate
python manage.py test
```

## Deployment Notes
- Set `DEBUG=False`, configure `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- Provide a strong `SECRET_KEY`.
- Serve over HTTPS for security settings to take effect.
- Typical commands:
```bash
python manage.py migrate
python manage.py collectstatic --noinput
# Example (Linux):
gunicorn smartroute.wsgi:application
```

## Screenshots
https://github.com/akshithkl/SmartRoute-Sullia/blob/main/Screenshot%202025-10-23%20104235.png?raw=true

## License
Specify a license (e.g., MIT) or state proprietary.
