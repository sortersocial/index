# AGENTS.md

## Project Overview

This project contains two main components:

1. **FastAPI Web Application** - A simple web server with HTML templates
2. **Rank Centrality Algorithm** - A statistical algorithm for analyzing pairwise comparisons

## Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Setup

### Option 1: Using uv (Recommended)

```bash
# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

### Option 2: Using pip

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

# Install dependencies
pip install -e .
```

## Running the Applications

### 1. FastAPI Web Server

The web server provides a simple HTML interface.

```bash
# Start the server
uvicorn src.main:app --reload

# Or with custom host/port
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

The application will be available at:
- http://localhost:8000 - Main page
- http://localhost:8000/docs - API documentation (Swagger UI)
- http://localhost:8000/redoc - API documentation (ReDoc)

### 2. Rank Centrality Script

This script implements a rank centrality algorithm for analyzing pairwise comparisons.

```bash
# Basic usage
python src/rank.py <num_items> [extra_comparisons] [iterations]

# Examples:
python src/rank.py 10                    # Test with 10 items
python src/rank.py 20 50                 # Test with 20 items and 50 extra comparisons
python src/rank.py 15 30 5               # Run 5 iterations with 15 items and 30 extra comparisons
```

**Parameters:**
- `num_items` (required) - Number of items to rank
- `extra_comparisons` (optional, default: 0) - Additional random comparisons beyond the spanning tree
- `iterations` (optional, default: 1) - Number of test iterations to run

**Output:**
The script outputs ranked items with their scores and scaled scores. Items are ranked from highest to lowest preference.

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── main.py           # FastAPI web application
│   ├── rank.py           # Rank centrality algorithm
│   └── templates/
│       └── index.html    # HTML template
├── pyproject.toml        # Project configuration and dependencies
├── idea.tdsl             # Project design notes
└── AGENTS.md             # This file
```

## Development Tools

The project is configured with:

- **Black** - Code formatter (line length: 88)
- **Ruff** - Fast Python linter
- **Mypy** - Static type checker

Run code quality checks:

```bash
# Format code
black src/

# Lint code
ruff check src/

# Type check
mypy src/
```

## Dependencies

- `fastapi` - Modern web framework for building APIs
- `jinja2` - Template engine for HTML rendering
- `numpy` - Numerical computing library
- `scipy` - Scientific computing library
- `uvicorn` - ASGI server for running FastAPI

All dependencies are specified in `pyproject.toml` and will be installed during setup.

## Notes

- The FastAPI app currently serves a basic welcome page
- The rank centrality algorithm uses a Markov chain approach to compute item rankings
- Both components are independent and can be run separately
