import os
import time
import logging
from pathlib import Path
from typing import Generator
from slugify import slugify

logger = logging.getLogger(__name__)

# Default to local 'data' folder if env var not set (for local dev)
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def init_storage():
    """Ensure the data directory exists."""
    if not DATA_DIR.exists():
        logger.info(f"Creating data directory at {DATA_DIR}")
        DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_email(subject: str, body: str) -> str:
    """
    Saves an email body to a text file.
    Format: {timestamp_ms}+{slugified_subject}.sorter
    """
    init_storage()
    
    # Use milliseconds to help collision avoidance and sorting precision
    timestamp = int(time.time() * 1000)
    slug = slugify(subject)
    
    filename = f"{timestamp}+{slug}.sorter"
    filepath = DATA_DIR / filename
    
    logger.info(f"Persisting email to {filepath}")
    filepath.write_text(body, encoding="utf-8")
    
    return str(filepath)


def stream_history() -> Generator[str, None, None]:
    """
    Yields the body of every .sorter file in the data directory,
    sorted by filename (which implies sorted by time due to prefix).
    """
    init_storage()
    
    # Glob returns in arbitrary order, so we must sort
    # Sorting by filename works because of the timestamp prefix
    files = sorted(DATA_DIR.glob("*.sorter"))
    
    logger.info(f"Found {len(files)} historical records to replay")
    
    for f in files:
        yield f.read_text(encoding="utf-8")

