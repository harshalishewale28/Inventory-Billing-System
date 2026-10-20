# Tkinter Billing System

This is a full Python `tkinter` migration of the original Java Swing billing project, rebuilt to use `sqlite3` instead of Microsoft Access.

## Features

- Login screen
- Dashboard with counts and report exports
- Customer add, edit, search, delete
- Item add, edit, search, delete
- Billing with customer selection, item search, cart, tax, totals, save
- Bill history with line-item view
- PDF export for invoices, customer report, item report, and sales report
- Settings to change username and password

## Database Choice

This app uses `SQLite`, which is the best fit for this project because:

- it ships with Python
- it needs no server setup
- it works well for a desktop inventory and billing application
- it is much easier to deploy than Access on macOS

The database file is created automatically here:

`data/billing_system.db`

Default login:

- Username: `admin`
- Password: `admin`

## Run

From the project root:

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
pip install -r tkinter_billing_system/requirements.txt
python tkinter_billing_system/app.py
```

## Project Layout

- `tkinter_billing_system/app.py` - main tkinter application
- `tkinter_billing_system/tkinter_billing_system/database.py` - sqlite schema and data access
- `tkinter_billing_system/tkinter_billing_system/reports.py` - PDF export helpers
- `tkinter_billing_system/data/` - generated SQLite database
- `tkinter_billing_system/exports/` - exported PDF files
