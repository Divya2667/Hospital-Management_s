import pytest
from flask import session, g
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import get_db
from app import create_app


def test_login_page_renders(client):
    """Test that login page loads with HTTP 200 and contains required elements."""
    response = client.get("/auth/login")
    assert response.status_code == 200
    assert b"Hospital Portal" in response.data
    assert b"Username" in response.data
    assert b"Password" in response.data
    assert b"toggle-password-visibility" in response.data
    assert b"Sign In" in response.data


def test_unauthenticated_access_redirects(client):
    """Unauthenticated users attempting to access protected routes must be redirected to login."""
    # Test protected /dashboard route
    res_dashboard = client.get("/dashboard")
    assert res_dashboard.status_code == 302
    assert "/auth/login?next=/dashboard" in res_dashboard.headers["Location"]

    # Test root route
    res_root = client.get("/")
    assert res_root.status_code == 302
    assert "/auth/login" in res_root.headers["Location"]


def test_login_validation_empty_fields(client):
    """Submitting empty username or password should display a clear error message."""
    response = client.post("/auth/login", data={"username": "", "password": ""}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Please provide both username and password." in response.data


def test_login_invalid_credentials(app, client):
    """Submitting incorrect username or password should display generic error message."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            ("nurse_joy", generate_password_hash("securepass123"), "Staff"),
        )
        db.commit()

    # Wrong password
    res1 = client.post("/auth/login", data={"username": "nurse_joy", "password": "wrongpassword"}, follow_redirects=True)
    assert res1.status_code == 200
    assert b"Invalid username or password." in res1.data

    # Non-existent user
    res2 = client.post("/auth/login", data={"username": "ghost_user", "password": "anypassword"}, follow_redirects=True)
    assert res2.status_code == 200
    assert b"Invalid username or password." in res2.data


def test_login_successful_and_session(app, client):
    """Valid credentials authenticate user, start session, and grant access to dashboard."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            ("dr_house", generate_password_hash("vicodin123"), "Doctor"),
        )
        db.commit()

    # Perform login
    response = client.post("/auth/login", data={"username": "dr_house", "password": "vicodin123"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Hospital Operations Dashboard" in response.data
    assert b"dr_house" in response.data
    assert b"Doctor" in response.data

    # Check session state
    with client.session_transaction() as sess:
        assert sess.get("username") == "dr_house"
        assert sess.get("role") == "Doctor"
        assert "user_id" in sess


def test_open_redirect_protection(app, client):
    """Login next parameter should reject external URLs to prevent open redirect vulnerabilities."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            ("safe_user", generate_password_hash("password123"), "Staff"),
        )
        db.commit()

    # Attempt login with external next URL
    response = client.post(
        "/auth/login?next=https://attacker.com/steal-creds",
        data={"username": "safe_user", "password": "password123"},
    )
    assert response.status_code == 302
    # Must redirect internally to /dashboard, NOT external site
    assert response.headers["Location"].endswith("/dashboard")


def test_logout(app, client):
    """POST to /auth/logout clears authenticated session and revokes access to protected routes."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO User (Username, Password_Hash, Role) VALUES (?, ?, ?)",
            ("admin_test", generate_password_hash("adminpass"), "Admin"),
        )
        db.commit()

    # Login first
    client.post("/auth/login", data={"username": "admin_test", "password": "adminpass"})

    # Verify session active
    with client.session_transaction() as sess:
        assert sess.get("username") == "admin_test"

    # Logout via POST
    logout_res = client.post("/auth/logout", follow_redirects=True)
    assert logout_res.status_code == 200
    assert b"You have been signed out successfully." in logout_res.data

    # Session must be cleared
    with client.session_transaction() as sess:
        assert "username" not in sess
        assert "user_id" not in sess

    # Access to protected route must be denied
    dash_res = client.get("/dashboard")
    assert dash_res.status_code == 302
    assert "/auth/login" in dash_res.headers["Location"]


def test_logout_get_method_not_allowed(client):
    """GET requests to /auth/logout must return 405 Method Not Allowed."""
    res = client.get("/auth/logout")
    assert res.status_code == 405


def test_create_admin_cli_command(runner, app):
    """Test flask create-admin CLI command creates user with hashed password."""
    result = runner.invoke(args=["create-admin", "--username", "superadmin", "--password", "AdminSecret99", "--role", "Admin"])
    assert "Administrator account 'superadmin' (Role: Admin) created successfully." in result.output

    with app.app_context():
        db = get_db()
        user = db.execute("SELECT * FROM User WHERE Username = 'superadmin'").fetchone()
        assert user is not None
        # Password MUST be hashed, never plaintext
        assert user["Password_Hash"] != "AdminSecret99"
        assert check_password_hash(user["Password_Hash"], "AdminSecret99")
        assert user["Role"] == "Admin"

    # Test duplicate creation handling
    dup_result = runner.invoke(args=["create-admin", "--username", "superadmin", "--password", "AnotherPass"])
    assert "Error: A user with username 'superadmin' already exists." in dup_result.output


def test_csrf_protection_enforced(tmp_path):
    """Verify that when CSRF protection is active, POST requests without CSRF token are blocked."""
    db_file = tmp_path / "csrf_test.db"
    csrf_app = create_app(
        test_config={
            "TESTING": True,
            "DATABASE": str(db_file),
            "WTF_CSRF_ENABLED": True,
            "SECRET_KEY": "test-csrf-secret",
        }
    )
    with csrf_app.app_context():
        from app.db import init_db
        init_db()

    csrf_client = csrf_app.test_client()
    # POST without CSRF token should return 400 Bad Request
    response = csrf_client.post("/auth/login", data={"username": "admin", "password": "password"})
    assert response.status_code == 400
