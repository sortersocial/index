"""EmailDSL parser using Lark.

Parses email-based submissions with hashtags, items, votes, and attributes.
"""

from dataclasses import dataclass
from typing import List, Optional

from lark import Lark, Transformer, v_args


# AST Node Definitions
@dataclass
class Hashtag:
    """Hashtag declaration: #ideas"""

    name: str


@dataclass
class Item:
    """Item submission: +item-title { optional body }"""

    title: str
    body: Optional[str] = None


@dataclass
class Attribute:
    """Attribute declaration: :difficulty :benefit"""

    name: str


@dataclass
class Vote:
    """Vote between items: +item1 10:1 +item2 { explanation }"""

    item1: str
    item2: str
    ratio_left: int
    ratio_right: int
    explanation: Optional[str] = None


@dataclass
class Email:
    """Email address: user@example.com"""

    address: str


@dataclass
class Document:
    """Parsed email document"""

    statements: List[object]


# Lark Grammar for EmailDSL
GRAMMAR = r"""
start: statement*

?statement: hashtag
          | vote           // Try vote before item to avoid ambiguity
          | item
          | attribute_decl
          | email_address
          | text_line

hashtag: "#" hashtag_name
hashtag_name: WORD+

item: "+" item_ref body?

vote: vote_prefix? "+" item_ref comparison "+" item_ref body?
vote_prefix: "!" "vote"

comparison: NUMBER ":" NUMBER   -> ratio_comparison
          | NUMBER ">" NUMBER   -> greater_comparison
          | NUMBER "=" NUMBER   -> equal_comparison
          | ">"                 -> simple_greater

attribute_decl: attribute+
attribute: ":" WORD

email_address: EMAIL

body: BODY_DOUBLE
    | BODY_SINGLE

item_ref: ITEM_NAME

text_line: TEXT_LINE

// Terminals - order matters for priority
EMAIL: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/

// Body with double braces: {{ text with {braces} }} - must come before BODY_SINGLE
BODY_DOUBLE.2: /\{\{(.|\n)*?\}\}/

// Body with single braces: { text } - matches anything except { or }
BODY_SINGLE.1: /\{[^{}]*\}/

ITEM_NAME: /[a-zA-Z0-9_]+([-][a-zA-Z0-9_]+)*/
NUMBER: /[0-9]+/
WORD: /[a-zA-Z0-9_]+/

// Text lines that don't start with special chars
TEXT_LINE: /[^#:+!@\n][^\n]*/

%import common.WS
%ignore WS
"""


@v_args(inline=True)
class EmailDSLTransformer(Transformer):
    """Transform parse tree into AST nodes."""

    def start(self, *statements):
        return Document(statements=list(statements))

    def hashtag(self, name):
        return Hashtag(name=str(name))

    def hashtag_name(self, *words):
        return "".join(str(w) for w in words)

    def item(self, title, body=None):
        body_text = self._extract_body(body) if body else None
        return Item(title=str(title), body=body_text)

    def vote(self, *args):
        # Filter out vote_prefix if present
        args = [a for a in args if a is not None and str(a) != "vote"]

        item1 = str(args[0])
        comparison = args[1]
        item2 = str(args[2])
        explanation = self._extract_body(args[3]) if len(args) > 3 else None

        ratio_left, ratio_right = comparison

        return Vote(
            item1=item1,
            item2=item2,
            ratio_left=ratio_left,
            ratio_right=ratio_right,
            explanation=explanation,
        )

    def vote_prefix(self, _):
        return None  # Filter this out

    def ratio_comparison(self, left, right):
        return (int(left), int(right))

    def greater_comparison(self, left, right):
        return (int(left), int(right))

    def equal_comparison(self, left, right):
        return (int(left), int(right))

    def simple_greater(self):
        return (1, 0)  # > means infinitely better, represent as 1:0

    def attribute_decl(self, *attributes):
        # Return list of attributes
        return [attr for attr in attributes]

    def attribute(self, name):
        return Attribute(name=str(name))

    def email_address(self, address):
        return Email(address=str(address))

    def item_ref(self, name):
        return str(name)

    def text_line(self, text):
        # Return None to filter out text lines
        return None

    def _extract_body(self, body_token):
        """Extract text from body token, removing delimiters."""
        if body_token is None:
            return None

        text = str(body_token)

        # Handle {{ }} delimiters
        if text.startswith("{{") and text.endswith("}}"):
            return text[2:-2].strip()

        # Handle { } delimiters
        if text.startswith("{") and text.endswith("}"):
            return text[1:-1].strip()

        return text.strip()


class EmailDSLParser:
    """Parser for EmailDSL."""

    def __init__(self):
        self.parser = Lark(
            GRAMMAR,
            parser="lalr",
            transformer=EmailDSLTransformer(),
        )

    def parse(self, text: str) -> Document:
        """Parse EmailDSL text into AST.

        Args:
            text: EmailDSL source text

        Returns:
            Document with parsed statements
        """
        tree = self.parser.parse(text)
        return tree

    def parse_lines(self, text: str) -> Document:
        """Parse EmailDSL with line-based filtering.

        Only parses lines that start with special characters,
        ignoring noise like email signatures.

        Args:
            text: EmailDSL source text

        Returns:
            Document with parsed statements
        """
        filtered_lines = []

        for line in text.split("\n"):
            stripped = line.lstrip()
            if stripped and stripped[0] in "#:+!@":
                filtered_lines.append(line)

        filtered_text = "\n".join(filtered_lines)
        return self.parse(filtered_text)
