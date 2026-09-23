import os

import click
from flask import Flask, g, redirect, render_template, url_for

from . import auth, db, staff, students, tutor
from .constants import STATUSES, goal_label


def ensure_demo_data():
    """Seed the demo database if it's empty or missing tables."""
    from .seed import seed
    conn = db.get_db()
    has_users = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if not has_users or not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        db.init_db()
        seed(conn)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "tutoring.sqlite")),
        # Public demo: shows one-click demo logins and seeds sample data on first start.
        DEMO_MODE=os.environ.get("DEMO_MODE") == "1",
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    from .seed import PASSWORD
    app.config["DEMO_PASSWORD"] = PASSWORD
    if app.config["DEMO_MODE"]:
        with app.app_context():
            ensure_demo_data()

    app.teardown_appcontext(db.close_db)
    for module in (auth, tutor, students, staff):
        app.register_blueprint(module.bp)

    app.jinja_env.globals.update(csrf_token=auth.csrf_token, statuses=STATUSES, goal_label=goal_label)
    app.jinja_env.filters["hours"] = lambda h: f"{h:g}"

    friendly = {
        400: "Something about that request didn't look right.",
        403: "That page isn't available for your account.",
        404: "We couldn't find that page.",
    }
    for code, message in friendly.items():
        def handler(e, code=code, message=message):
            detail = getattr(e, "description", None) if code == 400 else None
            return render_template("error.html", code=code, message=detail or message), code
        app.register_error_handler(code, handler)

    @app.route("/")
    @auth.login_required
    def home():
        if g.user["role"] == "staff":
            return redirect(url_for("staff.report"))
        return redirect(url_for("tutor.dashboard"))

    @app.cli.command("init-db")
    def init_db_command():
        """Create empty tables (drops existing data)."""
        db.init_db()
        click.echo("Initialised the database.")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Reset the database and fill it with demo tutors, students and sessions."""
        from .seed import seed
        db.init_db()
        seed(db.get_db())
        click.echo("Seeded demo data. Log in as staff@lvaep.org or maria@example.com (password: password123).")

    return app
