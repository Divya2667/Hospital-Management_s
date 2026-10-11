import functools
import click
from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from app.db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")


def login_required(view):
    """View decorator that redirects unauthenticated users to the login page."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)

    return wrapped_view


@bp.before_app_request
def load_logged_in_user():
    """Load authenticated user record into flask.g before every request."""
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute(
            "SELECT User_ID, Username, Role, Created_At FROM User WHERE User_ID = ?",
            (user_id,),
        ).fetchone()


@bp.route("/login", methods=("GET", "POST"))
def login():
    """Authenticate administrator or staff members and initiate session."""
    if request.method == "GET":
        # Clear authenticated identity so login portal always prompts for credentials
        session.pop("user_id", None)
        session.pop("username", None)
        session.pop("role", None)
        g.user = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        error = None

        if not username or not password:
            error = "Please provide both username and password."
        else:
            db = get_db()
            user = db.execute(
                "SELECT User_ID, Username, Password_Hash, Role FROM User WHERE Username = ?",
                (username,),
            ).fetchone()

            if user is None or not check_password_hash(user["Password_Hash"], password):
                error = "Invalid username or password."

        if error is None:
            # Clear old session data and store authenticated identity
            session.clear()
            session["user_id"] = user["User_ID"]
            session["username"] = user["Username"]
            session["role"] = user["Role"]

            next_page = request.args.get("next")
            # Prevent open redirects by ensuring the next URL is relative
            if not next_page or not next_page.startswith("/"):
                next_page = url_for("dashboard.index")

            return redirect(next_page)

        flash(error, "danger")

    return render_template("auth/login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    """Terminate the current authenticated session on POST request."""
    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("auth.login"))


from flask.cli import with_appcontext


@click.command("create-admin")
@click.option("--username", prompt="Admin username", help="Administrator username")
@click.option(
    "--password",
    prompt="Admin password",
    hide_input=True,
    confirmation_prompt=True,
    help="Administrator password",
)
@click.option(
    "--role",
    default="Admin",
    type=click.Choice(["Admin", "Doctor", "Staff"], case_sensitive=False),
    help="Account role (default: Admin)",
)
@with_appcontext
def create_admin_command(username, password, role):
    """Create or register an administrator account in the SQLite database."""
    username = username.strip()
    if not username or not password:
        click.echo("Error: Username and password cannot be empty.")
        return

    password_hash = generate_password_hash(password)
    db = get_db()
    try:
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        db.commit()
        click.echo(f"Administrator account '{username}' (Role: {role}) created successfully.")
    except db.IntegrityError:
        click.echo(f"Error: A user with username '{username}' already exists.")


def init_app(app):
    """Register CLI commands with the Flask application."""
    app.cli.add_command(create_admin_command)
