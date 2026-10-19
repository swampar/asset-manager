# Harvest IT Asset Manager

Track IT assets (laptops, monitors, phones, other) and assign them to staff.
Built with **Python (Flask) + SQLite**.

## Run it
```bash
pip install -r requirements.txt
python seed.py        # optional: adds demo staff and assets
python app.py         # open http://127.0.0.1:5000
```
Login: `admin` / `admin123` (created on first run). Change it and set a real `SECRET_KEY` before any real use.
Run the checks with `python tests.py`.

## Features
- Assets: add, edit, list (status and current holder shown), detail page with full assignment history
- Staff: add, list, and a per-person page of what they hold now and held before
- Assign an available asset, mark it returned (back to available or to under repair)
- Search (name, tag, serial) and filter by status and type
- CSV export (respects the current search and filters)
- Login (hashed password, session)

## Data model
- `assets` and `staff` hold the facts about each thing.
- `assignments` has one row each time an asset is handed out: `asset_id`, `staff_id`, `assigned_at`, `returned_at` (NULL while still held).
- **Assigned, returned, assigned again:** returning closes the open row (sets `returned_at`); assigning again adds a new row. Nothing is overwritten, so the history stays complete.
- **Safety:** a partial unique index allows only one open assignment per asset, so the database itself blocks double-assigning. Assign and return each run in one transaction.
- `assets.status` is kept for fast filtering; the open assignment row says who holds it.

## Why these choices
- Flask: small and readable, easy to explain. SQLite: no setup, a single file. Plain SQL instead of an ORM so every query is visible.

## Branding
All colours are CSS variables at the top of `static/style.css`. The current green and gold are a placeholder; I could not find the school's official colours, so replace the values there.

## Not done (honest list)
- Only one login role (no admin vs viewer), no password change screen, no CSRF protection
- No delete or archive for assets or staff, no staff edit screen
- No pagination, so very large lists would be slow
- Not deployed; runs locally only
