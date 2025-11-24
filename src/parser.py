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
start: _NL* (statement _NL+)* statement?

?statement: hashtag
          | vote           // Try vote before item to avoid ambiguity
          | item
          | attribute_decl
          | email_address

hashtag: "#" hashtag_name
hashtag_name: ITEM_NAME

item: "+" item_ref body?

vote: "+" item_ref comparison "+" item_ref body?

comparison: NUMBER ":" NUMBER   -> ratio_comparison
          | NUMBER ">" NUMBER   -> greater_comparison
          | NUMBER "<" NUMBER   -> less_comparison
          | NUMBER "=" NUMBER   -> equal_comparison
          | ">"                 -> simple_greater
          | "<"                 -> simple_less

attribute_decl: attribute+
attribute: ":" WORD

email_address: EMAIL

body: LBRACE LBRACE body_text_double RBRACE RBRACE  -> body_double
    | LBRACE body_text_single RBRACE                  -> body_single

body_text_double: BODY_TEXT_DOUBLE
body_text_single: BODY_TEXT_SINGLE

item_ref: ITEM_NAME

// Terminals - order matters for priority
EMAIL: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/

// Braces
LBRACE: "{"
RBRACE: "}"

// Body text for double braces - can contain single braces
// Use high priority to match before other terminals
BODY_TEXT_DOUBLE.10: /(.|\n)+?(?=\}\})/

// Body text for single braces - cannot contain braces
BODY_TEXT_SINGLE.5: /[^{}]+/

ITEM_NAME: /[a-zA-Z0-9_]+([-][a-zA-Z0-9_]+)*/
NUMBER: /[0-9]+/
WORD: /[a-zA-Z0-9_]+/

%import common.NEWLINE -> _NL
%import common.WS_INLINE
%ignore WS_INLINE
"""


class EmailDSLTransformer(Transformer):
    """Transform parse tree into AST nodes."""

    def start(self, children):
        # Filter out newlines and None values
        statements = [c for c in children if c is not None and not str(c).isspace()]
        return Document(statements=statements)

    def hashtag(self, children):
        return Hashtag(name=str(children[0]))

    def hashtag_name(self, words):
        return "".join(str(w) for w in words)

    def item(self, children):
        title = str(children[0])
        body = self._extract_body(children[1]) if len(children) > 1 else None
        return Item(title=title, body=body)

    def vote(self, children):
        item1 = str(children[0])
        comparison = children[1]
        item2 = str(children[2])
        explanation = self._extract_body(children[3]) if len(children) > 3 else None

        ratio_left, ratio_right = comparison

        return Vote(
            item1=item1,
            item2=item2,
            ratio_left=ratio_left,
            ratio_right=ratio_right,
            explanation=explanation,
        )

    def ratio_comparison(self, children):
        return (int(children[0]), int(children[1]))

    def greater_comparison(self, children):
        return (int(children[0]), int(children[1]))

    def less_comparison(self, children):
        # a < b means b is greater, so swap the ratio
        return (int(children[1]), int(children[0]))

    def equal_comparison(self, children):
        return (int(children[0]), int(children[1]))

    def simple_greater(self, children):
        return (1, 0)  # > means infinitely better, represent as 1:0

    def simple_less(self, children):
        return (0, 1)  # < means infinitely worse, represent as 0:1

    def attribute_decl(self, attributes):
        # Return list of attributes
        return [attr for attr in attributes]

    def attribute(self, children):
        return Attribute(name=str(children[0]))

    def email_address(self, children):
        return Email(address=str(children[0]))

    def item_ref(self, children):
        return str(children[0])

    def body_single(self, children):
        """Handle single brace body: { text }"""
        # children[0] is LBRACE, children[1] is body_text_single, children[2] is RBRACE
        return str(children[1]).strip()

    def body_double(self, children):
        """Handle double brace body: {{ text }}"""
        # children[0:2] are LBRACEs, children[2] is body_text_double, children[3:5] are RBRACEs
        return str(children[2]).strip()

    def body_text_single(self, children):
        return str(children[0])

    def body_text_double(self, children):
        return str(children[0])

    def _extract_body(self, body_token):
        """Extract text from body token, removing delimiters."""
        if body_token is None:
            return None

        # body_token is already processed by body_single/body_double
        return str(body_token)


class EmailDSLParser:
    """Parser for EmailDSL."""

    def __init__(self):
        self.parser = Lark(
            GRAMMAR,
            parser="lalr",
            # Don't use embedded transformer with lalr when testing
        )
        self.transformer = EmailDSLTransformer()

    def parse(self, text: str) -> Document:
        """Parse EmailDSL text into AST.

        Args:
            text: EmailDSL source text

        Returns:
            Document with parsed statements
        """
        tree = self.parser.parse(text)
        return self.transformer.transform(tree)

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
