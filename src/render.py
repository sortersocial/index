"""
Email body rendering with proper parser integration and declarative HTML building.
"""

from typing import List, Optional
import re
import markdown
from markupsafe import Markup
from python_hiccup.html.core import render as hiccup_render, raw
from src.parser import Document, Hashtag, Item, Vote, Attribute, Prose


def render_email_body_hiccup(body: str, doc: Optional[Document] = None) -> List:
    """
    Render email body as hiccup data structure (not HTML string).

    Args:
        body: Raw email body text
        doc: Pre-parsed Document (if already parsed), otherwise will parse

    Returns:
        Hiccup data structure: ['div', {'class': 'rendered-email-body'}, *elements]
    """
    from src.parser import EmailDSLParser

    if not body:
        return ['div', {'class': 'rendered-email-body'}]

    # Parse the document if not provided
    if doc is None:
        parser = EmailDSLParser()
        try:
            # Use parse_full to capture both DSL and prose
            doc = parser.parse_full(body)
        except Exception:
            # If parsing fails, return plain text paragraphs as hiccup
            return _render_plain_prose_hiccup(body)

    # Render each statement in order
    elements = []
    for stmt in doc.statements:
        element = _render_statement(stmt)
        if element:
            elements.append(element)

    return ['div', {'class': 'rendered-email-body'}, *elements]


def render_email_body(body: str, doc: Optional[Document] = None) -> str:
    """
    Render email body with intelligent formatting:
    - Parse sorter syntax using the real parser with full prose capture
    - Render sorter syntax elements with styled HTML
    - Render prose with collapsed line breaks and paragraph detection
    - Render item bodies with markdown

    Args:
        body: Raw email body text
        doc: Pre-parsed Document (if already parsed), otherwise will parse

    Returns:
        HTML string with formatted content
    """
    # Just render the hiccup structure to HTML
    hiccup_struct = render_email_body_hiccup(body, doc)
    return Markup(hiccup_render(hiccup_struct))


def _render_plain_prose_hiccup(body: str) -> List:
    """Fallback renderer for plain text without syntax (returns hiccup)."""
    paragraphs = re.split(r'\n\s*\n', body)
    elements = []

    for para in paragraphs:
        if para.strip():
            collapsed = ' '.join(line.strip() for line in para.split('\n') if line.strip())
            elements.append(['p', {'class': 'prose'}, collapsed])

    return ['div', {'class': 'rendered-email-body'}, *elements]


def _render_plain_prose(body: str) -> str:
    """Fallback renderer for plain text without syntax."""
    hiccup_struct = _render_plain_prose_hiccup(body)
    return Markup(hiccup_render(hiccup_struct))


def _render_statement(stmt) -> Optional[List]:
    """
    Render a parsed statement as a hiccup-style element.

    Args:
        stmt: Parsed statement (Prose, Hashtag, Item, Vote, Attribute, etc.)

    Returns:
        Hiccup-style element (list) or None
    """
    if isinstance(stmt, Prose):
        return _render_prose(stmt)
    elif isinstance(stmt, Hashtag):
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
        # Unknown statement type - skip
        return None


def _render_prose(prose: Prose) -> Optional[List]:
    """
    Render prose text with paragraph detection and line break collapsing.

    Email clients often break lines at ~72 chars, so we:
    - Split by double newlines to find paragraph breaks
    - Collapse single newlines within paragraphs
    - Render with markdown for links and basic formatting
    """
    if not prose.text.strip():
        return None

    # Split by double newlines to find paragraphs
    paragraphs = re.split(r'\n\s*\n', prose.text)
    elements = []

    for para in paragraphs:
        if para.strip():
            # Collapse single newlines within paragraph
            # (email clients break lines at ~72 chars)
            collapsed = ' '.join(line.strip() for line in para.split('\n') if line.strip())

            # Render with markdown to support links (no nl2br - already collapsed email wrapping)
            para_html = markdown.markdown(collapsed)
            # Remove the <p> tags that markdown adds (we'll add our own)
            para_html = re.sub(r'^<p>|</p>$', '', para_html.strip())

            elements.append(['p', {'class': 'prose'}, raw(para_html)])

    # Return a fragment container if multiple paragraphs, single p if one
    if len(elements) == 1:
        return elements[0]
    elif elements:
        return ['div', {'class': 'prose-block'}, *elements]
    else:
        return None


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
        # Render body with markdown (no nl2br - email clients insert unwanted newlines)
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
        # Render explanation with markdown (no nl2br - email clients insert unwanted newlines)
        explanation_html = markdown.markdown(vote.explanation)
        # Remove <p> tags that markdown adds
        explanation_html = re.sub(r'^<p>|</p>$', '', explanation_html.strip())
        children.append(
            ['div', {'class': 'vote-explanation'}, raw(explanation_html)]
        )

    return ['div', {'class': 'syntax-vote'}, *children]


def _render_attribute(attr: Attribute) -> List:
    """Render a single attribute badge."""
    return ['span', {'class': 'syntax-attribute'}, f':{attr.name}']


def _render_attributes(attrs: List[Attribute]) -> List:
    """Render multiple attribute badges on one line."""
    badges = [_render_attribute(attr) for attr in attrs]
    return ['div', {'class': 'syntax-line'}, *badges]
