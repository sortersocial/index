"""Storage for AI todo sorter lists."""
import uuid
from pathlib import Path
from slugify import slugify
from src.parser import EmailDSLParser
from src.reducer import Reducer

TODO_DIR = Path("data/todos")
TODO_DIR.mkdir(parents=True, exist_ok=True)


def create_todo_list(items: list[str], criteria: str, model: str) -> str:
    """Creates a new .sorter file for the todo list.

    Returns:
        list_id: The unique identifier for this todo list
    """
    list_id = uuid.uuid4().hex[:8]
    filename = TODO_DIR / f"{list_id}.sorter"

    # Build metadata header (compatible with storage.py format)
    header = [
        f"Criteria: {criteria}",
        f"Model: {model}",
        "---"
    ]

    # Construct DSL content
    body_lines = [
        f"#todo-{list_id}",
        ""
    ]

    for item in items:
        if item.strip():
            # Slugify to make valid item names (no spaces allowed in DSL)
            item_name = slugify(item.strip())
            body_lines.append(f"/{item_name}")

    # Set the criteria as the attribute context
    body_lines.append("")  # Blank line before attribute
    body_lines.append(f":{criteria.replace(' ', '-')}")

    content = "\n".join(header) + "\n" + "\n".join(body_lines) + "\n"  # Ensure trailing newline
    filename.write_text(content, encoding="utf-8")
    return list_id


def append_vote(list_id: str, vote_dsl: str):
    """Appends a single AI vote to the file."""
    filename = TODO_DIR / f"{list_id}.sorter"
    # Ensure vote is on a new line
    with open(filename, "a", encoding="utf-8") as f:
        # Read last char to check if we need a newline
        content = filename.read_text(encoding="utf-8")
        if content and not content.endswith('\n'):
            f.write('\n')
        f.write(f"{vote_dsl}\n")


def append_raw(list_id: str, text: str):
    """Appends raw text to the file (for chat messages)."""
    filename = TODO_DIR / f"{list_id}.sorter"
    with open(filename, "a", encoding="utf-8") as f:
        f.write(text)


def get_todo_state(list_id: str):
    """Parses the file and returns the Reducer state and metadata.

    Returns:
        (state, metadata) tuple where metadata contains criteria and model
    """
    filename = TODO_DIR / f"{list_id}.sorter"
    if not filename.exists():
        return None, None

    content = filename.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Extract metadata from header (before the --- separator)
    criteria = "importance"
    model = "anthropic/claude-3.5-haiku"
    separator_idx = None

    for i, line in enumerate(lines):
        if line.strip() == "---":
            separator_idx = i
            break
        if line.startswith("Criteria: "):
            criteria = line[10:].strip()
        elif line.startswith("Model: "):
            model = line[7:].strip()

    # Extract body (everything after ---)
    if separator_idx is not None:
        body = "\n".join(lines[separator_idx + 1:])
    else:
        # Legacy format without metadata header
        body = content

    # Reuse existing parser and reducer
    parser = EmailDSLParser()
    doc = parser.parse_lines(body)
    reducer = Reducer()
    reducer.process_document(doc)

    return reducer.state, {"criteria": criteria, "model": model}


def get_file_path(list_id: str) -> Path:
    """Returns the path to the .sorter file for debugging."""
    return TODO_DIR / f"{list_id}.sorter"
