"""Integration test for tutorial.sorter file."""

import pytest
from pathlib import Path
from src.parser import EmailDSLParser, Hashtag, Item, Vote, Attribute
from src.reducer import Reducer


def test_tutorial_sorter_parses():
    """Test that the tutorial.sorter file parses successfully."""
    parser = EmailDSLParser()

    # Read the tutorial file
    tutorial_path = Path(__file__).parent / "data" / "tutorial.sorter"
    content = tutorial_path.read_text(encoding="utf-8")

    # Parse the file
    doc = parser.parse_lines(content)

    # Basic sanity checks
    assert len(doc.statements) > 0, "Document should have parsed statements"

    # Count different statement types
    hashtags = [s for s in doc.statements if isinstance(s, Hashtag)]
    items = [s for s in doc.statements if isinstance(s, Item)]
    votes = [s for s in doc.statements if isinstance(s, Vote)]
    attributes = [s for s in doc.statements if isinstance(s, list) and s and isinstance(s[0], Attribute)]

    print(f"\nParsed tutorial.sorter:")
    print(f"  Hashtags: {len(hashtags)}")
    print(f"  Items: {len(items)}")
    print(f"  Votes: {len(votes)}")
    print(f"  Attribute declarations: {len(attributes)}")

    # Expected content based on tutorial.sorter
    assert len(hashtags) == 2, "Should have 2 hashtags: #alphabet and #sorter-properties"
    assert "alphabet" in [h.name for h in hashtags]
    assert "sorter-properties" in [h.name for h in hashtags]

    # Should have items like a, b, c, transitive, precise, asynchronous, collective, new, proprietary
    assert len(items) >= 9, f"Should have at least 9 items, got {len(items)}"
    item_names = [i.title for i in items]
    assert "a" in item_names
    assert "b" in item_names
    assert "c" in item_names
    assert "transitive" in item_names
    assert "precise" in item_names
    assert "asynchronous" in item_names
    assert "collective" in item_names

    # Should have multiple votes
    assert len(votes) >= 8, f"Should have at least 8 votes, got {len(votes)}"

    # Should have 3 attribute declarations: :overall, :truth and :important
    assert len(attributes) == 3, f"Should have 3 attribute declarations, got {len(attributes)}"

    print("\n✓ Tutorial file parsed successfully!")


def test_tutorial_with_reducer():
    """Test that the tutorial.sorter file processes through the reducer."""
    parser = EmailDSLParser()
    reducer = Reducer()

    # Read the tutorial file
    tutorial_path = Path(__file__).parent / "data" / "tutorial.sorter"
    content = tutorial_path.read_text(encoding="utf-8")

    # Parse and reduce
    doc = parser.parse_lines(content)
    reducer.process_document(doc, timestamp="1234567890", user_email="tutorial@sorter.social")

    # Verify state
    assert len(reducer.state.items) >= 9, "Should have created at least 9 items"
    assert len(reducer.state.votes) >= 8, "Should have recorded at least 8 votes"

    # Check specific items exist
    assert "a" in reducer.state.items
    assert "b" in reducer.state.items
    assert "c" in reducer.state.items
    assert "transitive" in reducer.state.items
    assert "collective" in reducer.state.items

    # Check hashtags are associated correctly
    assert "alphabet" in reducer.state.items["a"].hashtags
    assert "alphabet" in reducer.state.items["b"].hashtags
    assert "alphabet" in reducer.state.items["c"].hashtags
    assert "sorter-properties" in reducer.state.items["transitive"].hashtags

    # Check some items have bodies
    assert reducer.state.items["transitive"].body is not None
    assert "Transitive is the property" in reducer.state.items["transitive"].body

    # Check votes have attributes
    votes_with_overall = [v for v in reducer.state.votes if v.attribute == "overall"]
    votes_with_truth = [v for v in reducer.state.votes if v.attribute == "truth"]
    votes_with_important = [v for v in reducer.state.votes if v.attribute == "important"]

    assert len(votes_with_overall) >= 2, "Should have votes with :overall attribute"
    assert len(votes_with_truth) >= 3, "Should have votes with :truth attribute"
    assert len(votes_with_important) >= 4, "Should have votes with :important attribute"

    print(f"\n✓ Tutorial processed successfully!")
    print(f"  Total items: {len(reducer.state.items)}")
    print(f"  Total votes: {len(reducer.state.votes)}")
    print(f"  Votes with :overall: {len(votes_with_overall)}")
    print(f"  Votes with :truth: {len(votes_with_truth)}")
    print(f"  Votes with :important: {len(votes_with_important)}")


if __name__ == "__main__":
    test_tutorial_sorter_parses()
    test_tutorial_with_reducer()
    print("\n✅ All tutorial integration tests passed!")
