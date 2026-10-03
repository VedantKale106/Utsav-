import os
import secrets
from datetime import datetime, timedelta
from hmac import compare_digest
from flask import Flask, request, session, render_template
from dotenv import load_dotenv
from site_settings import get_site_settings

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY environment variable is not set.")
app.config.update(
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.context_processor
def inject_template_values():
    return {
        "current_year": datetime.now().year,
        "site": get_site_settings(),
    }


@app.before_request
def protect_admin_forms():
    if not request.path.startswith("/admin"):
        return None

    session_token = session.get("csrf_token", "")
    if not session_token:
        session_token = secrets.token_urlsafe(32)
        session["csrf_token"] = session_token

    if request.method == "POST":
        submitted_token = request.form.get("csrf_token", "")
        if not submitted_token or not compare_digest(submitted_token, session_token):
            return "Invalid or missing CSRF token.", 400
    return None

from routes.availability import availability_bp
from routes.order import order_bp
from routes.admin import admin_bp

app.register_blueprint(availability_bp)
app.register_blueprint(order_bp)
app.register_blueprint(admin_bp)

from flask import render_template

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/gallery")
def gallery():
    return render_template("gallery.html")

@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

@app.route("/booking")
def booking():
    slot = request.args.get("slot", "")
    return render_template("booking.html", preselected_slot=slot)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="The page you requested could not be found."), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("error.html", code=500, message="Something went wrong. Please try again shortly."), 500

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", use_reloader=False)
