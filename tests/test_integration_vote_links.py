"""Integration test for vote source email links."""

import pytest
from src.parser import EmailDSLParser
from src.reducer import Reducer
from src.rank import compute_rankings_from_state


def test_vote_has_source_filename():
    """Test that votes track their source filename."""
    parser = EmailDSLParser()
    reducer = Reducer()

    # Parse an email with a vote
    email_body = """#ideas
/task1 { first item }
/task2 { second item }
/task1 > /task2 { task1 is better }
"""

    doc = parser.parse_lines(email_body)

    # Process with a source filename
    reducer.process_document(
        doc,
        user_email="test@example.com",
        timestamp="1234567890",
        source_filename="1234567890-abc123.sorter"
    )

    # Check that the vote has the source filename
    assert len(reducer.state.votes) == 1
    vote = reducer.state.votes[0]

    assert vote.source_filename == "1234567890-abc123.sorter"
    assert vote.item1 == "task1"
    assert vote.item2 == "task2"
    assert vote.user_email == "test@example.com"

    print("✓ Vote correctly tracks source filename")


def test_vote_without_filename():
    """Test that votes work without source filename (backward compat)."""
    parser = EmailDSLParser()
    reducer = Reducer()

    email_body = """#ideas
/task1
/task2
/task1 > /task2
"""

    doc = parser.parse_lines(email_body)

    # Process without source filename
    reducer.process_document(
        doc,
        user_email="test@example.com",
        timestamp="1234567890"
    )

    # Check that the vote exists but has no filename
    assert len(reducer.state.votes) == 1
    vote = reducer.state.votes[0]

    assert vote.source_filename is None
    assert vote.item1 == "task1"
    assert vote.item2 == "task2"

    print("✓ Votes work without source filename (backward compat)")


def test_multiple_votes_different_files():
    """Test that multiple votes from different emails track correctly."""
    parser = EmailDSLParser()
    reducer = Reducer()

    # First email
    email1 = """#ideas
/a
/b
/a > /b
"""
    doc1 = parser.parse_lines(email1)
    reducer.process_document(
        doc1,
        user_email="user1@example.com",
        timestamp="1000",
        source_filename="1000-file1.sorter"
    )

    # Second email
    email2 = """#ideas
/c
/a > /c
"""
    doc2 = parser.parse_lines(email2)
    reducer.process_document(
        doc2,
        user_email="user2@example.com",
        timestamp="2000",
        source_filename="2000-file2.sorter"
    )

    # Check votes
    assert len(reducer.state.votes) == 2

    vote1 = reducer.state.votes[0]
    assert vote1.source_filename == "1000-file1.sorter"
    assert vote1.user_email == "user1@example.com"

    vote2 = reducer.state.votes[1]
    assert vote2.source_filename == "2000-file2.sorter"
    assert vote2.user_email == "user2@example.com"

    print("✓ Multiple votes track different source files correctly")


def test_html_rendering_includes_link():
    """Test that HTML template would include link (simulated)."""
    parser = EmailDSLParser()
    reducer = Reducer()

    email_body = """#test
/item1
/item2
/item1 > /item2
"""

    doc = parser.parse_lines(email_body)
    reducer.process_document(
        doc,
        user_email="test@example.com",
        timestamp="1234567890",
        source_filename="1234567890-test.sorter"
    )

    vote = reducer.state.votes[0]

    # Simulate what the template would render
    if vote.source_filename:
        link = f'<a href="/emails/{vote.source_filename}" target="_blank">view email</a>'
        assert "1234567890-test.sorter" in link
        assert "/emails/" in link
        print(f"✓ Template would render: {link}")
    else:
        pytest.fail("Vote should have source_filename")


if __name__ == "__main__":
    test_vote_has_source_filename()
    test_vote_without_filename()
    test_multiple_votes_different_files()
    test_html_rendering_includes_link()
    print("\n✅ All integration tests passed!")
