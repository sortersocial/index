import os
import time
import logging
from pathlib import Path
from typing import Generator, List, Tuple, Optional
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


def list_emails() -> List[Tuple[str, str]]:
    """
    Returns a list of (filename, subject) tuples for all emails.
    Sorted by timestamp (newest first).
    """
    init_storage()
    files = sorted(DATA_DIR.glob("*.sorter"), reverse=True)
    
    result = []
    for f in files:
        # Extract subject from filename: {timestamp}+{slug}.sorter
        name = f.stem  # removes .sorter
        parts = name.split("+", 1)
        subject = parts[1] if len(parts) > 1 else name
        result.append((f.name, subject))
    
    return result


def get_email(filename: str) -> Optional[str]:
    """
    Returns the content of a specific email file, or None if not found.
    """
    init_storage()
    filepath = DATA_DIR / filename
    
    # Security: ensure the file is actually in DATA_DIR (prevent path traversal)
    if not filepath.is_relative_to(DATA_DIR):
        return None
    
    if not filepath.exists() or not filepath.suffix == ".sorter":
        return None
    
    return filepath.read_text(encoding="utf-8")

