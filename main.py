import hmac
import os
import random
from datetime import timedelta
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash

from form import CafeForm, LoginForm

load_dotenv()

app = Flask(__name__)

# ---------- Secrets and settings (from .env) ----------
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is missing from your .env file.")

API_KEY = os.environ.get("CAFE_API_KEY")
# Remove any stray spaces or line breaks from the stored hash
ADMIN_PASSWORD_HASH = "".join((os.environ.get("ADMIN_PASSWORD_HASH") or "").split())
DEBUG = os.environ.get("FLASK_DEBUG") == "1"

# Stop debug mode from running on the live site
if DEBUG and os.environ.get("RENDER"):
    raise RuntimeError("FLASK_DEBUG must not be on in production.")

# ---------- Session cookie protection ----------
app.config["SESSION_COOKIE_HTTPONLY"] = True                                  # JavaScript can't read it
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"                                 # blocks most cross-site abuse
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE") == "1"  # HTTPS only, on Render
app.permanent_session_lifetime = timedelta(minutes=15)                        # admin logs out after 15 min

# ---------- Proxy (Render sits in front of the app) ----------
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# ---------- Database ----------
db_uri = os.environ.get("DB_URI", "sqlite:///cafes.db")
if db_uri.startswith("postgres://"):  # Render gives postgres://, SQLAlchemy needs postgresql://
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# ---------- Rate limiting (login attempts per visitor) ----------
# Memory by default. Set RATE_LIMIT_STORAGE to a Redis URL on Render so counts survive restarts.
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=os.environ.get("RATE_LIMIT_STORAGE", "memory://"),
)


# ---------- Security headers on every response ----------
@app.after_request
def add_security_headers(response):
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ---------- Helper functions ----------

def safe_equal(a, b):
    # Compare two secrets without leaking timing or crashing on odd characters.
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def like_pattern(text):
    # Escape % and _ so visitors can't use them as wildcards.
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def clean_text(value, max_length):
    # Accept only text, strip spaces, and enforce a length limit.
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > max_length:
        return None
    return value


def require_api_key(function):
    # Decorator: the route runs only if the X-API-KEY header is correct.
    @wraps(function)
    def decorated(*args, **kwargs):
        if not API_KEY:
            return jsonify(error="API authentication is not configured."), 503
        if not safe_equal(request.headers.get("X-API-KEY", ""), API_KEY):
            return jsonify(error="Invalid or missing API key."), 403
        return function(*args, **kwargs)
    return decorated


def admin_required(function):
    # Decorator: the route runs only if the visitor logged in as admin.
    @wraps(function)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Please log in as admin first.", "warning")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return decorated

 
@app.context_processor
def inject_admin():
    # Makes is_admin available to every template.
    return {"is_admin": bool(session.get("is_admin"))}


def cafe_name_taken(name, exclude_id=None):
    # Case-insensitive duplicate check. exclude_id skips the cafe being edited.
    query = db.select(Cafe).where(db.func.lower(Cafe.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Cafe.id != exclude_id)
    return db.session.execute(query).scalar_one_or_none() is not None


# ---------- Database model ----------

class Cafe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    map_url = db.Column(db.String(500), nullable=False)
    img_url = db.Column(db.String(500), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    seats = db.Column(db.String(80), nullable=False)
    has_toilet = db.Column(db.Boolean, default=False, nullable=False)
    has_wifi = db.Column(db.Boolean, default=False, nullable=False)
    has_sockets = db.Column(db.Boolean, default=False, nullable=False)
    can_take_calls = db.Column(db.Boolean, default=False, nullable=False)
    coffee_price = db.Column(db.String(30), nullable=True)

    def to_dict(self):
        # Turns the Cafe object into a plain dictionary for JSON.
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


with app.app_context():
    db.create_all()


def fill_cafe(cafe, form):
    # Copy the form's values onto a cafe, cleaning up the text.
    cafe.name = form.name.data.strip()
    cafe.location = form.location.data.strip()
    cafe.seats = form.seats.data.strip()
    cafe.map_url = form.map_url.data.strip()
    cafe.img_url = form.img_url.data.strip()
    cafe.coffee_price = (form.coffee_price.data or "").strip() or None
    cafe.has_wifi = form.has_wifi.data
    cafe.has_sockets = form.has_sockets.data
    cafe.has_toilet = form.has_toilet.data
    cafe.can_take_calls = form.can_take_calls.data


def try_commit(form=None):
    # Save. On failure, roll back, tell the user and return False.
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        if form is not None:
            form.name.errors.append("A cafe with this name already exists.")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Database error.")
        flash("Something went wrong. Please try again.", "danger")
    return False


# ---------- Login and logout ----------

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if ADMIN_PASSWORD_HASH and check_password_hash(ADMIN_PASSWORD_HASH, form.password.data):
            session.clear()
            session.permanent = True
            session["is_admin"] = True
            flash("Logged in as admin.", "success")
            return redirect(url_for("home"))
        app.logger.warning("Failed admin login from %s", request.remote_addr)
        flash("Wrong password.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))


# ---------- Public website routes ----------
@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    query = db.select(Cafe).order_by(Cafe.name)
    if q:
        query = query.where(Cafe.location.ilike(like_pattern(q), escape="\\"))
    cafes = db.session.execute(query).scalars().all()
    return render_template("index.html", cafes=cafes, q=q)


@app.route("/random-cafe")
def random_cafe_page():
    cafe = db.session.execute(
        db.select(Cafe).order_by(db.func.random()).limit(1)
    ).scalar_one_or_none()
    if cafe is None:
        flash("No cafes have been added yet.", "warning")
        return redirect(url_for("home"))
    return render_template("index.html", cafes=[cafe], q="")


@app.route("/add-cafe", methods=["GET", "POST"])
@admin_required
def add_cafe_page():
    form = CafeForm()
    if form.validate_on_submit():
        if cafe_name_taken(form.name.data.strip()):
            form.name.errors.append("A cafe with this name already exists.")
        else:
            cafe = Cafe()
            fill_cafe(cafe, form)
            db.session.add(cafe)
            if try_commit(form):
                flash("Cafe added.", "success")
                return redirect(url_for("home"))
    status = 400 if request.method == "POST" else 200
    return render_template("add.html", form=form, editing=False, cafe=None), status


@app.route("/edit/<int:cafe_id>", methods=["GET", "POST"])
@admin_required
def edit_cafe(cafe_id):
    cafe = db.get_or_404(Cafe, cafe_id)
    form = CafeForm(obj=cafe)
    if form.validate_on_submit():
        if cafe_name_taken(form.name.data.strip(), exclude_id=cafe.id):
            form.name.errors.append("Another cafe already uses this name.")
        else:
            fill_cafe(cafe, form)
            if try_commit(form):
                flash("Cafe updated successfully.", "success")
                return redirect(url_for("home"))
    status = 400 if request.method == "POST" else 200
    return render_template("add.html", form=form, editing=True, cafe=cafe), status


@app.route("/delete/<int:cafe_id>", methods=["POST"])
@admin_required
def delete_cafe(cafe_id):
    cafe = db.get_or_404(Cafe, cafe_id)
    name = cafe.name
    db.session.delete(cafe)
    if try_commit():
        flash(f"{name} was deleted.", "success")
    return redirect(url_for("home"))


# ---------- API routes (API key required) ----------

@app.route("/all", methods=["GET"])
@require_api_key
def get_all_cafes():
    cafes = db.session.execute(db.select(Cafe).order_by(Cafe.name)).scalars().all()
    return jsonify(cafes=[c.to_dict() for c in cafes])


@app.route("/search", methods=["GET"])
@require_api_key
def search_cafes():
    location = clean_text(request.args.get("loc", ""), 120)
    if location is None:
        return jsonify(error="Please provide a location using ?loc=..."), 400
    cafes = db.session.execute(
        db.select(Cafe).where(Cafe.location.ilike(like_pattern(location), escape="\\"))
    ).scalars().all()
    if not cafes:
        return jsonify(error=f"No cafes found for location: {location}"), 404
    return jsonify(cafes=[c.to_dict() for c in cafes])


@app.route("/random", methods=["GET"])
@require_api_key
def get_random_cafe():
    cafes = db.session.execute(db.select(Cafe)).scalars().all()
    if not cafes:
        return jsonify(error="No cafes have been added yet."), 404
    return jsonify(cafe=random.choice(cafes).to_dict())


if __name__ == "__main__":
    app.run(debug=DEBUG)