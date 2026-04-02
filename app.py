import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "utsav-fallback-secret")

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
    slot = __import__("flask").request.args.get("slot", "")
    razorpay_key = os.getenv("RAZORPAY_KEY_ID", "")
    return render_template("booking.html", preselected_slot=slot, razorpay_key=razorpay_key)

if __name__ == "__main__":
    app.run(debug=True)
