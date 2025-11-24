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


def save_email(subject: str, body: str, from_email: Optional[str] = None) -> str:
    """
    Saves an email body to a text file with metadata header.
    Format: {timestamp_ms}+{slugified_subject}.sorter

    File structure:
        From: user@example.com
        Timestamp: 1234567890
        ---
        [email body content]
    """
    init_storage()

    # Use milliseconds to help collision avoidance and sorting precision
    timestamp = int(time.time() * 1000)
    slug = slugify(subject)

    filename = f"{timestamp}+{slug}.sorter"
    filepath = DATA_DIR / filename

    # Build file content with metadata header
    content_parts = []
    if from_email:
        content_parts.append(f"From: {from_email}")
    content_parts.append(f"Timestamp: {timestamp}")
    content_parts.append("---")
    content_parts.append(body)

    content = "\n".join(content_parts)

    logger.info(f"Persisting email to {filepath}")
    filepath.write_text(content, encoding="utf-8")

    return str(filepath)


def parse_email_file(content: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Parse a .sorter file into (body, from_email, timestamp).

    Args:
        content: Raw file content

    Returns:
        Tuple of (body, from_email, timestamp)
    """
    lines = content.split("\n")

    # Look for metadata separator
    separator_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            separator_idx = i
            break

    # No separator = legacy file with just body
    if separator_idx is None:
        return (content, None, None)

    # Parse metadata headers
    from_email = None
    timestamp = None

    for i in range(separator_idx):
        line = lines[i]
        if line.startswith("From: "):
            from_email = line[6:].strip()
        elif line.startswith("Timestamp: "):
            timestamp = line[11:].strip()

    # Body is everything after separator
    body = "\n".join(lines[separator_idx + 1 :])

    return (body, from_email, timestamp)


def stream_history() -> Generator[Tuple[str, Optional[str], Optional[str]], None, None]:
    """
    Yields (body, from_email, timestamp) for every .sorter file in the data directory,
    sorted by filename (which implies sorted by time due to prefix).
    """
    init_storage()

    # Glob returns in arbitrary order, so we must sort
    # Sorting by filename works because of the timestamp prefix
    files = sorted(DATA_DIR.glob("*.sorter"))

    logger.info(f"Found {len(files)} historical records to replay")

    for f in files:
        content = f.read_text(encoding="utf-8")
        yield parse_email_file(content)


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


def get_email(filename: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """
    Returns (body, from_email, timestamp) for a specific email file, or None if not found.
    """
    init_storage()
    filepath = DATA_DIR / filename

    # Security: ensure the file is actually in DATA_DIR (prevent path traversal)
    if not filepath.is_relative_to(DATA_DIR):
        return None

    if not filepath.exists() or not filepath.suffix == ".sorter":
        return None

    content = filepath.read_text(encoding="utf-8")
    return parse_email_file(content)

