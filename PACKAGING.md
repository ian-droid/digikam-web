# Packaging with PyInstaller (Windows onedir)

Goal: a **folder** of files (not a single exe) you can zip and copy.

## 1. Build environment

Use the same OS/arch you will distribute for (e.g. Windows x64).

```bat
cd digikam-web
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

## 2. Build

```bat
pyinstaller digikam-web.spec
```

This produces:

```
dist\digikam-web\          <- server bundle
  digikam-web.exe
  _internal\               <- libs + bundled templates/static
  ...

dist\digikam-web-cli\      <- CLI bundle (optional)
  digikam-web-cli.exe
  _internal\
  ...
```

## 3. Recommended distribution layout

Copy both builds into one folder (or only the server if you init elsewhere):

```
DigiKamWeb\
  digikam-web.exe
  digikam-web-cli.exe
  _internal\          <- from the server build (keep next to digikam-web.exe)
  data\               <- created at runtime (app.db, thumb cache)
  README.txt
```

If you ship both exes, the simplest approach is:

1. Distribute `dist\digikam-web\` as-is (has `_internal` + `digikam-web.exe`).
2. Copy `digikam-web-cli.exe` **and** its `_internal` is already merged if you rebuild as one spec — with the current dual COLLECT, copy `digikam-web-cli.exe` into the server folder only works if all deps are already in the server `_internal`. Safer: ship two folders, or merge into one Analysis (advanced).

**Practical approach for one directory:**

```bat
mkdir dist\DigiKamWeb
xcopy /E /I dist\digikam-web\* dist\DigiKamWeb\
copy dist\digikam-web-cli\digikam-web-cli.exe dist\DigiKamWeb\
```

If the CLI fails missing DLLs, ship `dist\digikam-web-cli` as a separate folder, or run init from a machine that still has Python.

## 4. First run on the target PC

```bat
digikam-web-cli.exe init --digikam-db "D:\Photos\digikam4.db" --username admin --password "secret" --cert fullchain.pem --key privkey.pem

digikam-web.exe --host 0.0.0.0 --port 8443
```

App data defaults next to the exe: `data\app.db`, `data\thumb_cache\`.

Or set:

```bat
set DIGIKAM_WEB_APP_DB_PATH=C:\DigiKamWeb\data\app.db
```

## 5. Common issues

| Issue | Fix |
|--------|-----|
| `ModuleNotFoundError: uvicorn.loops...` | Already listed in `hiddenimports` in the `.spec` |
| Templates / CSS 404 | Ensure `templates` and `static` are in `datas=` (they are) |
| bcrypt / Pillow missing | `pip install bcrypt pillow` before building |
| Antivirus deletes exe | Code-sign or whitelist; common with PyInstaller |
| Ctrl+C hang | Known Windows asyncio quirk; second Ctrl+C forces exit |

## 6. One-file alternative (not recommended here)

```bat
pyinstaller --onefile --add-data "templates;templates" --add-data "static;static" run_server.py
```

Onedir starts faster and is easier to debug; onefile unpacks to a temp dir every run.

## 7. Optional: simpler single-folder CLI+server

Rebuild with one `Analysis` including both scripts, two `EXE`, one `COLLECT` — advanced; the provided dual COLLECT is simpler to maintain.
