# Hospital Management System (HMS)

A full-stack, modular Hospital Management System built with **Flask**, **SQLite**, **Jinja2**, and **Bootstrap 5**.

---

## Getting Started (Windows)

### 1. Prerequisites
- Python 3.11+ installed and available on your system path.

### 2. Virtual Environment Setup
Open PowerShell or Command Prompt in the project root directory:

```powershell
# Create the virtual environment (if not already created)
python -m venv .venv

# Activate the virtual environment
# In PowerShell:
.\.venv\Scripts\Activate.ps1
# Or in Command Prompt:
.\.venv\Scripts\activate.bat
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Environment Configuration
Copy `.env.example` to `.env` (already created for local development):
```powershell
copy .env.example .env
```

### 5. Run the Application
```powershell
python run.py
```
Open your browser and navigate to: `http://127.0.0.1:5000`

### 6. Run Automated Tests
```powershell
pytest -v
```

---

## Project Structure
```text
Hospital Management/
├── app/
│   ├── __init__.py          # Flask application factory
│   ├── templates/           # Jinja2 templates (to be expanded in subsequent phases)
│   └── static/              # CSS and JS static assets
├── tests/
│   ├── conftest.py          # Pytest fixtures and app configurations
│   └── test_foundation.py   # Foundation verification tests
├── config.py                # Environment and app configuration classes
├── run.py                   # Application execution entry point
├── requirements.txt         # Project dependencies
├── .env.example             # Template environment variables
├── .env                     # Local environment settings
├── .gitignore               # Ignored version control artifacts
├── PROJECT_PROGRESS.md      # Phase-by-phase progress tracking document
└── README.md                # Project documentation
```
