"""Semantic analysis and state reduction for EmailDSL.

Processes parsed documents and maintains state across multiple emails.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from src.parser import Attribute, Document, Email, Hashtag, Item, Vote


class ParseError(Exception):
    """Semantic parsing error."""

    pass


@dataclass
class ItemRecord:
    """Full item record with metadata."""

    title: str
    body: Optional[str]
    hashtags: Set[str]
    created_by: Optional[str] = None  # Email address of creator
    timestamp: Optional[str] = None


@dataclass
class VoteRecord:
    """Full vote record with metadata."""

    item1: str
    item2: str
    ratio_left: int
    ratio_right: int
    attribute: Optional[str]
    explanation: Optional[str]
    user_email: Optional[str] = None  # Email address of voter
    timestamp: Optional[str] = None
    source_filename: Optional[str] = None  # Filename of source email


@dataclass
class State:
    """Application state accumulated from processing emails."""

    items: Dict[str, ItemRecord] = field(default_factory=dict)
    votes: List[VoteRecord] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)


class Reducer:
    """Reduces parsed documents into application state."""

    def __init__(self):
        self.state = State()
        self.current_hashtag: Optional[str] = None
        self.current_attribute: Optional[str] = None
        self.current_user_email: Optional[str] = None
        self.current_source_filename: Optional[str] = None

    def process_document(
        self,
        doc: Document,
        timestamp: Optional[str] = None,
        user_email: Optional[str] = None,
        source_filename: Optional[str] = None,
    ):
        """Process a parsed document and update state.

        Args:
            doc: Parsed document
            timestamp: Optional timestamp for this document
            user_email: Optional email address of the document author
            source_filename: Optional filename of source email

        Raises:
            ParseError: If semantic validation fails
        """
        # Reset per-document context
        self.current_hashtag = None
        self.current_attribute = None
        self.current_user_email = user_email
        self.current_source_filename = source_filename

        for statement in doc.statements:
            if statement is None:
                continue

            if isinstance(statement, Hashtag):
                self._process_hashtag(statement)

            elif isinstance(statement, Item):
                self._process_item(statement, timestamp)

            elif isinstance(statement, list) and all(
                isinstance(a, Attribute) for a in statement
            ):
                self._process_attributes(statement)

            elif isinstance(statement, Vote):
                self._process_vote(statement, timestamp)

            elif isinstance(statement, Email):
                self._process_email(statement)

    def _process_hashtag(self, hashtag: Hashtag):
        """Set current hashtag context."""
        self.current_hashtag = hashtag.name

    def _process_item(self, item: Item, timestamp: Optional[str]):
        """Process item submission.

        Items must have a hashtag context.
        """
        if self.current_hashtag is None:
            raise ParseError(
                f"Item '{item.title}' submitted without hashtag context. "
                "Use #hashtag before submitting items."
            )

        # Check if item already exists
        if item.title in self.state.items:
            # Error if trying to redeclare with a body (bodies are immutable)
            if item.body:
                raise ParseError(
                    f"Item '{item.title}' already exists with a body. "
                    "Bodies are immutable. To add to another hashtag, use: /{item.title}"
                )
            # Add current hashtag to existing item (cross-tagging)
            self.state.items[item.title].hashtags.add(self.current_hashtag)
        else:
            # Create new item
            self.state.items[item.title] = ItemRecord(
                title=item.title,
                body=item.body,
                hashtags={self.current_hashtag},
                created_by=self.current_user_email,
                timestamp=timestamp,
            )

    def _process_attributes(self, attributes: List[Attribute]):
        """Process attribute declarations.

        Attributes set the context for subsequent votes.
        For now, just track the last declared attribute.
        """
        if attributes:
            # Take the last attribute as the active one
            self.current_attribute = attributes[-1].name

    def _process_vote(self, vote: Vote, timestamp: Optional[str]):
        """Process vote between items.

        Both items must exist (no forward references).
        An attribute context must be set before voting.
        """
        # Validate attribute context exists
        if self.current_attribute is None:
            raise ParseError(
                f"Cannot vote without attribute context. "
                "Use an attribute declaration (e.g., :impact, :feasibility) before voting."
            )

        # Validate items exist
        if vote.item1 not in self.state.items:
            raise ParseError(
                f"Cannot vote on '{vote.item1}': item does not exist. "
                "Items must be declared before voting."
            )

        if vote.item2 not in self.state.items:
            raise ParseError(
                f"Cannot vote on '{vote.item2}': item does not exist. "
                "Items must be declared before voting."
            )

        # Validate ratio doesn't contain 0 (breaks random walk)
        if vote.ratio_left == 0 or vote.ratio_right == 0:
            raise ParseError(
                f"Vote ratio cannot contain 0 ({vote.ratio_left}:{vote.ratio_right}). "
                "Zero ratios break the ranking algorithm's random walk. Use small numbers like 1:10 instead."
            )

        # Record vote with current attribute context
        self.state.votes.append(
            VoteRecord(
                item1=vote.item1,
                item2=vote.item2,
                ratio_left=vote.ratio_left,
                ratio_right=vote.ratio_right,
                attribute=self.current_attribute,
                explanation=vote.explanation,
                user_email=self.current_user_email,
                timestamp=timestamp,
                source_filename=self.current_source_filename,
            )
        )

    def _process_email(self, email: Email):
        """Process email address."""
        # For now, just track emails we've seen
        if email.address not in self.state.emails:
            self.state.emails.append(email.address)

    def get_items_by_hashtag(self, hashtag: str) -> List[ItemRecord]:
        """Get all items with a specific hashtag."""
        return [item for item in self.state.items.values() if hashtag in item.hashtags]

    def get_votes_by_attribute(self, attribute: str) -> List[VoteRecord]:
        """Get all votes for a specific attribute."""
        return [vote for vote in self.state.votes if vote.attribute == attribute]

    def get_votes_for_item(self, item_title: str) -> List[VoteRecord]:
        """Get all votes involving a specific item."""
        return [
            vote
            for vote in self.state.votes
            if vote.item1 == item_title or vote.item2 == item_title
        ]


def reduce_documents(
    documents: List[tuple[Document, Optional[str], Optional[str]]]
) -> tuple[State, List[str]]:
    """Reduce multiple documents into final state.

    Args:
        documents: List of (document, timestamp, user_email) tuples

    Returns:
        Tuple of (final_state, list_of_errors)
    """
    reducer = Reducer()
    errors = []

    for doc, timestamp, user_email in documents:
        try:
            reducer.process_document(doc, timestamp, user_email)
        except ParseError as e:
            errors.append(str(e))

    return reducer.state, errors


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from src.parser import EmailDSLParser
    from src.rank import compute_rankings_from_state

    if len(sys.argv) < 4:
        print("usage: python -m src.reducer <file.sorter> <hashtag> <attribute>")
        print("\nExample: python -m src.reducer ideas.txt ideas impact")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    hashtag = sys.argv[2]
    attribute = sys.argv[3]

    # Parse file
    content = file_path.read_text(encoding="utf-8")
    parser = EmailDSLParser()
    doc = parser.parse_lines(content)

    # Reduce
    reducer = Reducer()
    try:
        reducer.process_document(doc, timestamp="0", user_email="cli")
    except ParseError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Rank and print
    rankings = compute_rankings_from_state(
        reducer.state,
        hashtag=hashtag,
        attribute=attribute
    )

    if not rankings:
        print(f"No rankings found for #{hashtag} with attribute :{attribute}")
        sys.exit(0)

    # Group by component for display
    from itertools import groupby

    rankings_by_component = {}
    for title, score, rank, comp_id in rankings:
        if comp_id not in rankings_by_component:
            rankings_by_component[comp_id] = []
        rankings_by_component[comp_id].append((title, score, rank))

    # Print results
    print(f"Rankings for #{hashtag} by :{attribute}\n")

    if len(rankings_by_component) == 1:
        # Single component - simple display
        for title, score, rank in rankings_by_component[0]:
            print(f"{rank}. {title} ({score:.4f})")
    else:
        # Multiple components - show separately
        print(f"Found {len(rankings_by_component)} disconnected groups:\n")
        for comp_id, items in sorted(rankings_by_component.items()):
            print(f"Component {comp_id + 1}:")
            for title, score, rank in items:
                print(f"  {rank}. {title} ({score:.4f})")
            print()
