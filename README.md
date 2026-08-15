# DigiKam Web

Read-only web frontend for DigiKam photo collections.

## Features (prototype)

- Strict **read-only** access to DigiKam databases and media files
- Command-line initialization (no web configuration UI)
- User authentication (users managed via CLI only)
- HTTPS only (operator supplies certificate + key)
- **Albums** tree and **Dates** tree (year → month → day), with expandable folders and remembered collapse state
- Fixed-size thumbnail grid with infinite scroll and a sliding DOM window
- On-the-fly thumbnails from original still images (Pillow → WebP, disk-cached)
- EXIF / metadata panel from DigiKam’s database; map links when GPS is present
- Mobile-friendly layout (drawer navigation)
- Unsupported media (e.g. video): placeholder thumb/preview; metadata still available
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
# Default: listen on all IPv4 interfaces (0.0.0.0), port 8443
python -m app.main

# Examples:
#   python -m app.main --host 0.0.0.0 --port 8443   # all IPv4 interfaces (default)
#   python -m app.main --host 127.0.0.1              # IPv4 localhost only
#   python -m app.main --host ::                     # all IPv6 interfaces
#   python -m app.main --port 443
```

Then open `https://<your-server-ip>:8443` (or `https://localhost:8443` from the same machine) and log in.

**Firewall / NAT:** binding to `0.0.0.0` only makes the process listen on all IPv4 NICs. You still need to open the port in the OS firewall and, if accessing from the Internet, forward it on your router. Prefer a reverse proxy (Caddy/nginx) with a real certificate when exposing publicly.

### Bind address and IPv6

| `--host` / `DIGIKAM_WEB_HOST` | Listens on |
|-------------------------------|------------|
| `0.0.0.0` (default) | All **IPv4** interfaces only |
| `127.0.0.1` | IPv4 localhost only |
| `::` | All **IPv6** interfaces (on some OSes may also accept IPv4-mapped addresses) |
| `::1` | IPv6 localhost only |

The server binds a **single** address. True dual-stack (IPv4 + IPv6 at once) is not built in; use two processes, or a reverse proxy, if you need both explicitly.

### User management

```bash
python -m app.cli.init_cmd user list
python -m app.cli.init_cmd user add --username alice
python -m app.cli.init_cmd user passwd --username alice
python -m app.cli.init_cmd user delete --username alice
```

## Configuration

Paths and secrets are stored in the application database (`data/app.db` by default).

Environment variables (prefix `DIGIKAM_WEB_`):

| Variable            | Meaning                          |
|---------------------|----------------------------------|
| `APP_DB_PATH`       | Path to app SQLite DB            |
| `HOST`              | Bind address (default `0.0.0.0` = all IPv4 interfaces) |
| `PORT`              | Listen port (default `8443`)     |
| `TLS_CERT` / `TLS_KEY` | Certificate and key files     |
| `SECRET_KEY`        | Session signing key              |

## Project layout

```
app/
  cli/           # init + user / config management commands
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

Still images: generated **on-the-fly from the original files** with Pillow, served as **WebP** (disk cache under the app data directory).

DigiKam’s **PGF** thumbnail database is **not** used. There is no practical pure-Python PGF decoder, and this project deliberately avoids external converters for that path.

Video and other non-image files: a generated **placeholder** thumbnail (and placeholder in the lightbox). Metadata from DigiKam’s DB can still be opened; originals are not decoded or streamed for preview.

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

## Notes / limitations of this prototype

- Browsing is limited to the **Albums** and **Dates** trees plus the image grid.
- No tagging, search, faces, or write operations.
- Album path resolution relies on DigiKam’s `specificPath` / `identifier` values; network mounts must be reachable from the host running this app.
- Default listen address is IPv4-only (`0.0.0.0`); see [Bind address and IPv6](#bind-address-and-ipv6).

## Safety

- DigiKam databases are opened with SQLite `mode=ro`.
- Media files are only served after path validation against the resolved album roots.
- Absolute filesystem paths never leave the server.
- Sessions use signed, HttpOnly, Secure cookies.

## Roadmap (long term, low priority)

Items below are **not** scheduled; listed for orientation only.

- **Video support** (low priority): real poster frames (e.g. via ffmpeg), HTML5 playback with HTTP Range, optional transcode for awkward codecs. Today videos only get placeholders + metadata.
- Additional DigiKam views (tags, people, search)
- Optional MySQL/MariaDB DigiKam core backend (repository interface is already separable)
- Packaging refinements (see `PACKAGING.md`)
