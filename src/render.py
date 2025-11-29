"""
Email body rendering with proper parser integration and declarative HTML building.
"""

from typing import List, Optional
import re
import markdown
from markupsafe import Markup
from python_hiccup.html.core import render as hiccup_render, raw
from src.parser import Document, Hashtag, Item, Vote, Attribute


def render_email_body(body: str, doc: Optional[Document] = None) -> str:
    """
    Render email body with intelligent formatting:
    - Parse sorter syntax using the real parser
    - Collapse single newlines in prose, preserve double newlines as paragraphs
    - Render sorter syntax elements with styled HTML
    - Render item bodies with markdown

    Args:
        body: Raw email body text
        doc: Pre-parsed Document (if already parsed), otherwise will parse

    Returns:
        HTML string with formatted content
    """
    from src.parser import EmailDSLParser

    if not body:
        return ""

    # Parse the document if not provided
    if doc is None:
        parser = EmailDSLParser()
        try:
            doc = parser.parse_lines(body)
        except Exception:
            # If parsing fails, just return the body as plain text paragraphs
            return _render_plain_prose(body)

    # Split body into lines for processing
    lines = body.split('\n')

    # Build a mapping of line indices to parsed statements
    # We'll match syntax lines to their corresponding statements
    syntax_line_indices = set()
    line_to_statement = {}

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped and stripped[0] in '#:/@!':
            syntax_line_indices.add(i)

    # Match statements to lines (approximate - based on line order)
    statement_idx = 0
    for i in syntax_line_indices:
        if statement_idx < len(doc.statements):
            stmt = doc.statements[statement_idx]
            if stmt is not None:
                line_to_statement[i] = stmt
            statement_idx += 1

    # Now render, processing both syntax lines and prose
    elements = []
    prose_buffer = []

    def flush_prose():
        """Flush accumulated prose lines as paragraphs."""
        if not prose_buffer:
            return

        # Join and split by double newlines to find paragraphs
        text = '\n'.join(prose_buffer)
        paragraphs = re.split(r'\n\s*\n', text)

        for para in paragraphs:
            if para.strip():
                # Collapse single newlines within paragraph
                collapsed = ' '.join(line.strip() for line in para.split('\n') if line.strip())
                elements.append(['p', {'class': 'prose'}, collapsed])

        prose_buffer.clear()

    # Process each line
    for i, line in enumerate(lines):
        if i in line_to_statement:
            # Flush any accumulated prose
            flush_prose()

            # Render the parsed statement
            stmt = line_to_statement[i]
            element = _render_statement(stmt, line)
            if element:
                elements.append(element)
        elif i not in syntax_line_indices:
            # Regular prose line
            prose_buffer.append(line)

    # Flush remaining prose
    flush_prose()

    # Convert to HTML using hiccup and mark as safe
    return Markup(hiccup_render(['div', {'class': 'rendered-email-body'}, *elements]))


def _render_plain_prose(body: str) -> str:
    """Fallback renderer for plain text without syntax."""
    paragraphs = re.split(r'\n\s*\n', body)
    elements = []

    for para in paragraphs:
        if para.strip():
            collapsed = ' '.join(line.strip() for line in para.split('\n') if line.strip())
            elements.append(['p', {'class': 'prose'}, collapsed])

    return Markup(hiccup_render(['div', {'class': 'rendered-email-body'}, *elements]))


def _render_statement(stmt, original_line: str) -> Optional[List]:
    """
    Render a parsed statement as a hiccup-style element.

    Args:
        stmt: Parsed statement (Hashtag, Item, Vote, Attribute, etc.)
        original_line: Original line from email (for fallback rendering)

    Returns:
        Hiccup-style element (list) or None
    """
    if isinstance(stmt, Hashtag):
        return _render_hashtag(stmt)
    elif isinstance(stmt, Item):
        return _render_item(stmt)
    elif isinstance(stmt, Vote):
        return _render_vote(stmt)
    elif isinstance(stmt, Attribute):
        return _render_attribute(stmt)
    elif isinstance(stmt, list):
        # Attribute declarations return lists of Attribute objects
        return _render_attributes(stmt)
    else:
        # Unknown statement type - render as plain text
        return ['div', {'class': 'syntax-line'}, original_line]


def _render_hashtag(hashtag: Hashtag) -> List:
    """Render a hashtag with link."""
    return [
        'div',
        {'class': 'syntax-hashtag'},
        ['a', {'href': f'/hashtag/{hashtag.name}'}, f'#{hashtag.name}']
    ]


def _render_item(item: Item) -> List:
    """Render an item with title and optional markdown body in a panel."""
    children = [
        ['div', {'class': 'item-title'}, f'/{item.title}']
    ]

    if item.body:
        # Render body with markdown
        body_html = markdown.markdown(
            item.body,
            extensions=['fenced_code', 'codehilite'],
            extension_configs={
                'codehilite': {
                    'css_class': 'highlight',
                    'guess_lang': False
                }
            }
        )
        # Use raw HTML for markdown content
        children.append(['div', {'class': 'item-body'}, raw(body_html)])

    return ['div', {'class': 'syntax-item'}, *children]


def _render_vote(vote: Vote) -> List:
    """Render a vote with items, ratio, and optional explanation."""
    # Canonicalize item order for URL
    item1, item2 = sorted([vote.item1, vote.item2])

    # Build comparison string
    if vote.ratio_left == vote.ratio_right:
        comparison = '='
    elif vote.ratio_left > vote.ratio_right:
        comparison = f'{vote.ratio_left}:{vote.ratio_right}'
    else:
        comparison = f'{vote.ratio_left}:{vote.ratio_right}'

    children = [
        [
            'a',
            {'href': f'/compare/{item1}/vs/{item2}', 'class': 'vote-link'},
            ['span', {'class': 'vote-item'}, f'/{vote.item1}'],
            ' ',
            ['span', {'class': 'vote-comparison'}, comparison],
            ' ',
            ['span', {'class': 'vote-item'}, f'/{vote.item2}']
        ]
    ]

    if vote.explanation:
        children.append(
            ['div', {'class': 'vote-explanation'}, vote.explanation]
        )

    return ['div', {'class': 'syntax-vote'}, *children]


def _render_attribute(attr: Attribute) -> List:
    """Render a single attribute badge."""
    return ['span', {'class': 'syntax-attribute'}, f':{attr.name}']


def _render_attributes(attrs: List[Attribute]) -> List:
    """Render multiple attribute badges on one line."""
    badges = [_render_attribute(attr) for attr in attrs]
    return ['div', {'class': 'syntax-line'}, *badges]
