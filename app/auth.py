import secrets
from functools import wraps

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)


@bp.before_app_request
def load_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


@bp.before_app_request
def csrf_protect():
    # Minimal CSRF protection: every POST form carries a per-session token.
    if request.method == "POST":
        token = session.get("_csrf")
        if not token or not secrets.compare_digest(token, request.form.get("_csrf", "")):
            abort(400, "Form expired. Go back, refresh the page and try again.")


def csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect email or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            nxt = request.args.get("next", "")
            # Only follow local redirects.
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("home"))
    return render_template("login.html")


def validate_signup(form, db):
    """Returns (cleaned fields, errors) for the tutor sign-up form."""
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    errors = []
    if not name:
        errors.append("Enter your name.")
    if "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Enter a valid email address.")
    elif db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        errors.append("An account with that email already exists. Try logging in instead.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    elif password != form.get("confirm", ""):
        errors.append("Passwords don't match.")
    return {"name": name, "email": email, "password": password}, errors


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Tutor self-registration. New tutors see no student data until staff assign them."""
    if g.user is not None:
        return redirect(url_for("home"))
    errors = []
    if request.method == "POST":
        db = get_db()
        data, errors = validate_signup(request.form, db)
        if not errors:
            user_id = db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'tutor')",
                (data["name"], data["email"], generate_password_hash(data["password"])),
            ).lastrowid
            db.commit()
            session.clear()
            session["user_id"] = user_id
            flash("Welcome aboard! The office will assign your students shortly.", "success")
            return redirect(url_for("home"))
    return render_template("signup.html", errors=errors), (422 if errors else 200)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
