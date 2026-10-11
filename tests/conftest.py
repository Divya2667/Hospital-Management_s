import pytest
from app import create_app
from app.db import init_db


@pytest.fixture
def app(tmp_path):
    """Create and configure a fresh app instance with a dedicated temp SQLite database for each test."""
    db_file = tmp_path / "test_hospital.db"

    test_app = create_app(
        test_config={
            "TESTING": True,
            "DATABASE": str(db_file),
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret-key-hospital-mgmt",
        }
    )

    with test_app.app_context():
        init_db()

    yield test_app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test CLI runner for the app."""
    return app.test_cli_runner()
