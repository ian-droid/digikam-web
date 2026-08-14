# DigiKam Web

Read-only web frontend for DigiKam photo collections.

## Features (prototype)

- Strict **read-only** access to DigiKam databases and media files
- Command-line initialization (no web configuration UI)
- User authentication (users managed via CLI only)
- HTTPS only (operator supplies certificate + key)
- Album tree + paginated image grid (~60 items per page, load-more / scroll)
- Thumbnails from DigiKam’s PGF thumbnail database (with optional fallback to originals)
- SQLite first; repository layer designed for future DB backends

## Requirements

- Python 3.10+
- A DigiKam installation with a SQLite core database (`digikam4.db`)
- TLS certificate and private key

## Quick start

```bash
# 1. Install dependencies
cd digikam-web
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# 2. Initialize (point at your digikam4.db)
python -m app.cli.init_cmd init \
  --digikam-db /path/to/digikam4.db \
  --username admin \
  --password 'your-secure-password' \
  --cert /path/to/fullchain.pem \
  --key /path/to/privkey.pem

# 3. Start the HTTPS server
# Default: listen on all interfaces (0.0.0.0), port 8443
python -m app.main

# Examples:
#   python -m app.main --host 0.0.0.0 --port 8443   # all interfaces (default)
#   python -m app.main --host 127.0.0.1              # localhost only
#   python -m app.main --port 443
```

Then open `https://<your-server-ip>:8443` (or `https://localhost:8443` from the same machine) and log in.

**Firewall / NAT:** binding to `0.0.0.0` only makes the process listen on all NICs. You still need to open the port in the OS firewall and, if accessing from the Internet, forward it on your router. Prefer a reverse proxy (Caddy/nginx) with a real certificate when exposing publicly.

### User management

```bash
python -m app.cli.init_cmd user list
python -m app.cli.init_cmd user add --username alice
python -m app.cli.init_cmd user delete --username alice
```

## Configuration

Paths and secrets are stored in the application database (`data/app.db` by default).

Environment variables (prefix `DIGIKAM_WEB_`):

| Variable            | Meaning                          |
|---------------------|----------------------------------|
| `APP_DB_PATH`       | Path to app SQLite DB            |
| `HOST`              | Bind address (default `0.0.0.0` = all interfaces) |
| `PORT`              | Listen port (default `8443`)     |
| `TLS_CERT` / `TLS_KEY` | Certificate and key files     |
| `SECRET_KEY`        | Session signing key              |

## Project layout

```
app/
  cli/           # init + user management commands
  db/            # application database
  repositories/  # DigiKam read-only repository (extendable)
  services/      # path resolution, thumbnails
  api/           # FastAPI routes
  auth/          # session handling
  main.py        # ASGI entry point
templates/       # Jinja2 pages
static/          # CSS + JS
```

## Thumbnails

Thumbnails are generated on-the-fly from the original media files using Pillow and served as **WebP** (with disk cache). No DigiKam PGF decoder is used (PGF has no practical pure-Python implementation and we avoid external converters).


## Notes / limitations of this prototype

- Only the Album tree and image grid are implemented.
- No tagging, search, faces, or write operations.
- Album path resolution relies on the `specificPath` / `identifier` values stored by DigiKam; network mounts must be reachable from the host running this app.

## Safety

- DigiKam databases are opened with SQLite `mode=ro`.
- Media files are only served after path validation against the resolved album roots.
- Absolute filesystem paths never leave the server.
- Sessions use signed, HttpOnly, Secure cookies.


## Map links (GPS)

If DigiKam has GPS for a photo, the EXIF dialog shows a dropdown of map sites.
Templates are stored in the app DB key `map_link_templates` (JSON).

```bash
# Show current templates
python -m app.cli.init_cmd config get map_link_templates

# Set custom templates (must include {lat} and {lon}; optional {zoom})
python -m app.cli.init_cmd config set map_link_templates '[
  {"id":"google","name":"Google Maps","url":"https://www.google.com/maps?q={lat},{lon}"},
  {"id":"osm","name":"OpenStreetMap","url":"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"}
]'
```
