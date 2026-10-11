import os
import sqlite3
from pathlib import Path
import click
from flask import current_app, g


def get_db():
    """Get or create the SQLite database connection for the current request context."""
    if "db" not in g:
        db_path = current_app.config["DATABASE"]

        # In Vercel serverless environment, auto-seed the SQLite database on first request
        if os.environ.get("VERCEL") and db_path != ":memory:":
            db_p = Path(db_path)
            if not db_p.exists() or db_p.stat().st_size == 0:
                try:
                    db_p.parent.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
                g.db = sqlite3.connect(db_path)
                g.db.row_factory = sqlite3.Row
                g.db.execute("PRAGMA foreign_keys = ON;")
                with current_app.open_resource("schema.sql", mode="r") as f:
                    g.db.executescript(f.read())
                g.db.commit()
                try:
                    from app.seeder import import_csv_dataset
                    import_csv_dataset(g.db)
                except Exception:
                    pass
                return g.db

        g.db = sqlite3.connect(db_path)
        # Enable column access by name
        g.db.row_factory = sqlite3.Row
        # CRITICAL: Always enforce SQLite foreign-key constraints
        g.db.execute("PRAGMA foreign_keys = ON;")

    return g.db


def close_db(e=None):
    """Close the database connection if opened during the request context."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Execute schema.sql to initialize the database tables and indexes."""
    db = get_db()
    with current_app.open_resource("schema.sql", mode="r") as f:
        db.executescript(f.read())
    db.commit()


@click.command("init-db")
def init_db_command():
    """Clear existing data and create new database tables according to schema.sql."""
    init_db()
    click.echo("Initialized the SQLite database successfully.")


from flask.cli import with_appcontext


@click.command("load-dataset")
@click.option("--dir", "dataset_dir", default=None, help="Custom path to dataset folder")
@with_appcontext
def load_dataset_command(dataset_dir):
    """Ingest CSV files from dataset/ directory into SQLite database."""
    from app.seeder import import_csv_dataset
    db = get_db()
    stats = import_csv_dataset(db, dataset_dir)
    click.echo(
        f"Dataset loaded successfully: {stats['patients']} patients, "
        f"{stats['doctors']} doctors, {stats['appointments']} appointments, "
        f"{stats['bills']} bills, {stats['treatments']} treatments."
    )


def init_app(app):
    """Register database functions and CLI commands with the Flask application."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(load_dataset_command)
