import os
from flask import Flask, jsonify
from flask_wtf.csrf import CSRFProtect
from config import config_by_name, Config

csrf = CSRFProtect()


def create_app(config_name=None, test_config=None):
    """Application factory for Hospital Management System."""
    app = Flask(__name__, instance_relative_config=True)

    # Ensure instance folder exists for SQLite storage
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Load configuration
    selected_config = config_name or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_by_name.get(selected_config, Config))

    # Apply test config if supplied
    if test_config is not None:
        if isinstance(test_config, dict):
            app.config.from_mapping(test_config)
        else:
            app.config.from_object(test_config)

    # Initialize extensions
    csrf.init_app(app)

    # Initialize SQLite database management
    from app import db
    db.init_app(app)

    # Initialize Authentication Blueprint & CLI commands
    from app import auth
    app.register_blueprint(auth.bp)
    auth.init_app(app)

    # Initialize Dashboard Blueprint
    from app import dashboard
    app.register_blueprint(dashboard.bp)

    # Initialize Patient Management Blueprint
    from app import patients
    app.register_blueprint(patients.bp)

    # Initialize Doctor Management Blueprint
    from app import doctors
    app.register_blueprint(doctors.bp)

    # Initialize Appointment Management Blueprint
    from app import appointments
    app.register_blueprint(appointments.bp)

    # Initialize Billing Management Blueprint
    from app import billing
    app.register_blueprint(billing.bp)

    # Template context processor to make current_app and has_endpoint available globally
    @app.context_processor
    def inject_context():
        from flask import current_app
        return {
            "current_app": current_app,
            "has_endpoint": lambda ep: ep in current_app.view_functions,
        }

    # Operational Health Check Endpoint
    @app.route("/health")
    def health():
        return jsonify(
            {
                "status": "healthy",
                "app": "Hospital Management System",
                "environment": app.config.get("ENV", "development"),
                "csrf_enabled": app.config.get("WTF_CSRF_ENABLED", True),
                "clinic_hours": f"{app.config.get('CLINIC_OPEN_TIME')} - {app.config.get('CLINIC_CLOSE_TIME')}",
            }
        )

    return app
