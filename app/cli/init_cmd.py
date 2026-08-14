"""Command-line initialization and user management."""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Optional

import click

from app.config import settings
from app.db.app_db import AppDB
from app.repositories.digikam_repo import DigikamRepository


def _resolve_specific_path(identifier: str, specific_path: str) -> Optional[Path]:
    """
    Best-effort resolution of DigiKam AlbumRoot paths.
    identifier examples:
      volumeid:?path=/home/user/Pictures
      networkshareid:?mountpath=/mnt/nas
    """
    # Prefer the specificPath column when it is an absolute existing path
    p = Path(specific_path)
    if p.is_absolute() and p.exists():
        return p.resolve()

    # Try to parse identifier
    if "path=" in identifier:
        raw = identifier.split("path=", 1)[1]
        # URL-decode basic cases
        raw = raw.replace("%2F", "/").replace("%3A", ":")
        candidate = Path(raw)
        if candidate.exists():
            return candidate.resolve()

    if "mountpath=" in identifier:
        raw = identifier.split("mountpath=", 1)[1]
        raw = raw.replace("%2F", "/").replace("%3A", ":")
        candidate = Path(raw)
        if candidate.exists():
            return candidate.resolve()

    # Last resort: the specificPath as given
    if p.exists():
        return p.resolve()

    return None


@click.group()
def cli():
    """DigiKam Web – command-line tools."""
    pass


@cli.command("init")
@click.option(
    "--digikam-db",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to digikam4.db (core database)",
)
@click.option(
    "--thumbs-db",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to thumbnails-digikam.db (auto-detected next to core DB if omitted)",
)
@click.option(
    "--app-db",
    type=click.Path(path_type=Path),
    default=None,
    help="Path for the application database (default: data/app.db)",
)
@click.option("--username", default=None, help="Create an initial admin user")
@click.option("--password", default=None, help="Password for the initial user")
@click.option(
    "--cert",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="TLS certificate file (optional at init, can be set later)",
)
@click.option(
    "--key",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="TLS private key file",
)
def init_cmd(
    digikam_db: Path,
    thumbs_db: Optional[Path],
    app_db: Optional[Path],
    username: Optional[str],
    password: Optional[str],
    cert: Optional[Path],
    key: Optional[Path],
):
    """Initialize the application: locate DigiKam data and create app database."""
    app_db_path = app_db or settings.app_db_path
    click.echo(f"Application database : {app_db_path}")
    click.echo(f"DigiKam core database: {digikam_db}")

    db = AppDB(app_db_path)
    db.init_schema()

    # Generate a secret if none exists
    if not db.get_config("secret_key"):
        secret = secrets.token_urlsafe(48)
        db.set_config("secret_key", secret)
        click.echo("Generated new session secret_key")

    db.set_config("digikam_db_path", str(digikam_db.resolve()))

    # Thumbnail database (PGF blobs)
    if thumbs_db is None:
        candidate = digikam_db.parent / "thumbnails-digikam.db"
        if candidate.is_file():
            thumbs_db = candidate
    if thumbs_db and thumbs_db.is_file():
        db.set_config("thumbs_db_path", str(thumbs_db.resolve()))
        click.echo(f"Thumbnails database  : {thumbs_db}")
    else:
        click.echo("WARNING: thumbnails-digikam.db not found – PGF thumbs unavailable")

    if cert:
        db.set_config("tls_cert", str(cert.resolve()))
    if key:
        db.set_config("tls_key", str(key.resolve()))

    # Read AlbumRoots (read-only)
    try:
        repo = DigikamRepository(digikam_db)
        roots = repo.get_album_roots()
    except Exception as exc:
        click.echo(f"ERROR reading DigiKam database: {exc}", err=True)
        sys.exit(1)

    db.clear_album_roots()
    resolved = 0
    for r in roots:
        specific = r.get("specificPath") or ""
        identifier = r.get("identifier") or ""
        path = _resolve_specific_path(identifier, specific)
        if path is None:
            click.echo(
                f"  WARNING: could not resolve AlbumRoot id={r['id']} "
                f"label={r.get('label')!r} → {specific!r}"
            )
            # still store it so the operator can fix later
            path_str = specific
        else:
            path_str = str(path)
            resolved += 1
            click.echo(f"  Root {r['id']}: {r.get('label') or '(no label)'} → {path_str}")

        db.upsert_album_root(
            digikam_id=r["id"],
            label=r.get("label") or "",
            status=r.get("status") or 0,
            type_=r.get("type") or 0,
            identifier=identifier,
            specific_path=path_str,
            relative_path="",
        )

    click.echo(f"Stored {len(roots)} album root(s), {resolved} resolved to existing paths.")

    if username:
        username = username.strip()
        if not password:
            password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        # Prefer re-prompt if password looks empty after strip (Windows quoting quirks)
        password = password if password is not None else ""
        if db.user_count() == 0 or click.confirm(f"Create user '{username}'?", default=True):
            try:
                # Replace existing user with same name so re-init is idempotent
                if any(u["username"].lower() == username.lower() for u in db.list_users()):
                    db.delete_user(username)
                    click.echo(f"Replacing existing user '{username}'")
                db.create_user(username, password, is_admin=True)
                # create_user already round-trips the hash; double-check from this process
                if db.verify_user(username, password):
                    click.echo(f"Created admin user '{username}' (password verified)")
                else:
                    click.echo(f"WARNING: user '{username}' created but verify failed", err=True)
            except Exception as exc:
                click.echo(f"Could not create user: {exc}", err=True)

    click.echo("Initialization complete.")
    click.echo("Start the server with:  python -m app.main")
    click.echo("  (provide --cert / --key or set them in the app database)")


@cli.command("user")
@click.argument("action", type=click.Choice(["add", "delete", "list", "passwd"]))
@click.option("--username", default=None)
@click.option("--password", default=None)
@click.option("--app-db", type=click.Path(path_type=Path), default=None)
def user_cmd(action: str, username: Optional[str], password: Optional[str], app_db: Optional[Path]):
    """Manage users (add / delete / list)."""
    app_db_path = app_db or settings.app_db_path
    db = AppDB(app_db_path)
    if not app_db_path.exists():
        click.echo("Application database does not exist. Run 'init' first.", err=True)
        sys.exit(1)
    db.init_schema()

    if action == "list":
        users = db.list_users()
        if not users:
            click.echo("No users.")
            return
        for u in users:
            admin = " (admin)" if u["is_admin"] else ""
            click.echo(f"  {u['username']}{admin}  created={u['created_at']}")
        return

    if not username:
        username = click.prompt("Username")

    username = username.strip()

    if action == "add":
        if not password:
            password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        try:
            db.create_user(username, password, is_admin=False)
            click.echo(f"User '{username}' created (password verified).")
        except Exception as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)
    elif action == "passwd":
        if not password:
            password = click.prompt("New password", hide_input=True, confirmation_prompt=True)
        if db.update_password(username, password):
            click.echo(f"Password updated for '{username}'.")
        else:
            click.echo(f"User '{username}' not found or password update failed.", err=True)
            sys.exit(1)
    elif action == "delete":
        if db.delete_user(username):
            click.echo(f"User '{username}' deleted.")
        else:
            click.echo(f"User '{username}' not found.")



@cli.command("config")
@click.argument("action", type=click.Choice(["get", "set", "list"]))
@click.argument("key", required=False, default=None)
@click.argument("value", required=False, default=None)
@click.option("--app-db", type=click.Path(path_type=Path), default=None)
def config_cmd(action: str, key: Optional[str], value: Optional[str], app_db: Optional[Path]):
    """Read/write app config values (e.g. map_link_templates)."""
    import json
    from app.map_links import CONFIG_KEY, default_templates_json, ensure_map_templates, parse_templates

    app_db_path = app_db or settings.app_db_path
    db = AppDB(app_db_path)
    if not app_db_path.exists():
        click.echo("Application database does not exist. Run 'init' first.", err=True)
        sys.exit(1)
    db.init_schema()

    if action == "list":
        cfg = db.get_all_config()
        # hide secret
        for k, v in sorted(cfg.items()):
            if k == "secret_key":
                v = "(hidden)"
            if len(v) > 120:
                v = v[:117] + "..."
            click.echo(f"  {k} = {v}")
        return

    if action == "get":
        if not key:
            key = click.prompt("Key")
        if key == CONFIG_KEY:
            ensure_map_templates(db)
        val = db.get_config(key)
        if val is None:
            click.echo("(not set)")
            sys.exit(1)
        click.echo(val)
        return

    if action == "set":
        if not key:
            key = click.prompt("Key")
        if value is None:
            value = click.prompt("Value")
        if key == CONFIG_KEY:
            # validate JSON templates
            try:
                parsed = parse_templates(value)
            except Exception as exc:
                click.echo(f"Invalid templates: {exc}", err=True)
                sys.exit(1)
            if not parsed:
                click.echo("No valid templates (need name, url with {lat} and {lon})", err=True)
                sys.exit(1)
            value = json.dumps(parsed, ensure_ascii=False, indent=2)
        db.set_config(key, value)
        click.echo(f"Set {key}")
        if key == CONFIG_KEY:
            click.echo(f"  ({len(parse_templates(value))} map link template(s))")
        return



if __name__ == "__main__":
    cli()
