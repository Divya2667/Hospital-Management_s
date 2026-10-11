import sqlite3
import click
from flask import current_app, g


def get_db():
    """Get or create the SQLite database connection for the current request context."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"]
        )
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
