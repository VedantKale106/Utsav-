# Utsav Banquet Hall

Flask booking application for Utsav Banquet Hall. Customers can check slot availability and submit booking requests. Administrators can approve, decline, cancel, complete, and manage bookings and site content.

## Features

- MongoDB-backed booking requests, bookings, reservations, and audit logs
- Atomic per-date reservation protection for partial and full-day slots
- Duplicate-request detection and configurable pending-request expiry
- Site content and booking rules are kept in `site_settings.json`
- Admin authentication with hashed passwords, CSRF protection, rate limiting, and session expiry
- WhatsApp message links for booking requests, declines, and cancellations
- Privacy consent, retention anonymization, friendly error pages, and responsive layouts
- Vercel serverless deployment through `api/index.py`

## Local Setup

Use Python 3.11 or newer.

```powershell
python -m pip install -r requirements.txt
python run_app.py
```

The launcher opens:

- `http://127.0.0.1:5000/`
- `http://127.0.0.1:5000/admin/login`

You can also double-click `start_app.bat` on Windows.

## Environment Variables

Create a local `.env` file. Never commit it.

```env
MONGO_URI=mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/utsav?retryWrites=true&w=majority
FLASK_SECRET_KEY=long-random-secret
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=werkzeug-password-hash
WHATSAPP_NUMBER=919999999999
COOKIE_SECURE=0
DATA_RETENTION_DAYS=730
FLASK_DEBUG=0
```

For Vercel, configure the same values in Project Settings > Environment Variables and use `COOKIE_SECURE=1`. Do not add `ADMIN_PASSWORD` when using `ADMIN_PASSWORD_HASH`.

## Admin

Open `/admin/login` and then use:

- `/admin/change-password` to change the administrator password

Admin actions are recorded in MongoDB audit logs. Decline and cancellation actions require a reason.

## Deployment

The repository includes `vercel.json` and `api/index.py` for Vercel. Import the GitHub repository into Vercel, configure the environment variables, and deploy.

MongoDB Atlas must allow connections from the deployed Vercel function. Rotate any database credentials that have previously been exposed.

## Validation

Compile the backend modules with:

```powershell
python -m py_compile app.py db.py booking_lifecycle.py site_settings.py routes\availability.py routes\order.py routes\admin.py api\index.py
```
