"""Tests for EmailDSL parser and reducer."""

import pytest

from src.parser import (
    Attribute,
    Document,
    Email,
    EmailDSLParser,
    Hashtag,
    Item,
    Vote,
)
from src.reducer import ParseError, Reducer


@pytest.fixture
def parser():
    return EmailDSLParser()


@pytest.fixture
def reducer():
    return Reducer()


class TestHashtags:
    """Test hashtag parsing."""

    def test_single_word_hashtag(self, parser):
        doc = parser.parse("#ideas")
        assert len(doc.statements) == 1
        assert isinstance(doc.statements[0], Hashtag)
        assert doc.statements[0].name == "ideas"

    def test_multi_word_hashtag(self, parser):
        doc = parser.parse("#projectideas")
        assert len(doc.statements) == 1
        assert doc.statements[0].name == "projectideas"


class TestItems:
    """Test item parsing."""

    def test_item_without_body(self, parser):
        doc = parser.parse("-simple-task")
        assert len(doc.statements) == 1
        assert isinstance(doc.statements[0], Item)
        assert doc.statements[0].title == "simple-task"
        assert doc.statements[0].body is None

    def test_item_with_body(self, parser):
        doc = parser.parse("-task { this is the body }")
        assert len(doc.statements) == 1
        item = doc.statements[0]
        assert item.title == "task"
        assert item.body == "this is the body"

    def test_item_with_multiline_body(self, parser):
        text = """-task {
this is a multiline
body with several lines
}"""
        doc = parser.parse(text)
        item = doc.statements[0]
        assert "multiline" in item.body
        assert "several lines" in item.body

    def test_item_underscore_title(self, parser):
        doc = parser.parse("-my_task_name")
        assert doc.statements[0].title == "my_task_name"

    def test_item_with_numbers(self, parser):
        doc = parser.parse("-task123")
        assert doc.statements[0].title == "task123"


class TestVotes:
    """Test vote parsing."""

    def test_vote_ratio_syntax(self, parser):
        doc = parser.parse("-item1 10:1 -item2")
        assert len(doc.statements) == 1
        vote = doc.statements[0]
        assert isinstance(vote, Vote)
        assert vote.item1 == "item1"
        assert vote.item2 == "item2"
        assert vote.ratio_left == 10
        assert vote.ratio_right == 1

    def test_vote_simple_greater(self, parser):
        doc = parser.parse("-item1 > -item2")
        vote = doc.statements[0]
        assert vote.ratio_left == 2
        assert vote.ratio_right == 1

    def test_vote_with_explanation(self, parser):
        doc = parser.parse("-item1 10:1 -item2 { item1 is much harder }")
        vote = doc.statements[0]
        assert vote.explanation == "item1 is much harder"


class TestAttributes:
    """Test attribute parsing."""

    def test_single_attribute(self, parser):
        doc = parser.parse(":difficulty")
        assert len(doc.statements) == 1
        attrs = doc.statements[0]
        assert isinstance(attrs, list)
        assert len(attrs) == 1
        assert attrs[0].name == "difficulty"

    def test_multiple_attributes(self, parser):
        doc = parser.parse(":difficulty :benefit")
        attrs = doc.statements[0]
        assert len(attrs) == 2
        assert attrs[0].name == "difficulty"
        assert attrs[1].name == "benefit"


class TestEmails:
    """Test email address parsing."""

    def test_simple_email(self, parser):
        doc = parser.parse("user@example.com")
        assert len(doc.statements) == 1
        email = doc.statements[0]
        assert isinstance(email, Email)
        assert email.address == "user@example.com"

    def test_complex_email(self, parser):
        doc = parser.parse("first.last+tag@subdomain.example.co.uk")
        email = doc.statements[0]
        assert email.address == "first.last+tag@subdomain.example.co.uk"


class TestNestedBraces:
    """Test nested brace handling."""

    def test_double_brace_body(self, parser):
        doc = parser.parse("-item {{ code with { braces } inside }}")
        item = doc.statements[0]
        assert "{ braces }" in item.body

    def test_double_brace_vote_explanation(self, parser):
        doc = parser.parse("-a 10:1 -b {{ explanation with { nested } braces }}")
        vote = doc.statements[0]
        assert "{ nested }" in vote.explanation


class TestFullDocuments:
    """Test complete document parsing."""

    def test_simple_document(self, parser):
        text = """
#ideas
-task1 { first task }
-task2 { second task }
"""
        doc = parser.parse(text)
        assert len(doc.statements) == 3
        assert isinstance(doc.statements[0], Hashtag)
        assert isinstance(doc.statements[1], Item)
        assert isinstance(doc.statements[2], Item)

    def test_document_with_votes(self, parser):
        text = """
#projects
-proj1 { first project }
-proj2 { second project }
:difficulty
-proj1 10:1 -proj2 { proj1 is much harder }
"""
        doc = parser.parse(text)
        statements = [s for s in doc.statements if s is not None]
        assert len(statements) == 5  # hashtag, 2 items, attribute_decl list, vote

    def test_document_with_noise(self, parser):
        text = """
Hello there!

#ideas
-task1 { real task }

Sent from my iPhone
"""
        doc = parser.parse_lines(text)
        # Should only parse the lines starting with special chars
        statements = [s for s in doc.statements if s is not None]
        assert len(statements) == 2


class TestReducer:
    """Test semantic analysis and state reduction."""

    def test_item_requires_hashtag(self, parser, reducer):
        doc = parser.parse("-item1 { body }")
        with pytest.raises(ParseError, match="without hashtag context"):
            reducer.process_document(doc)

    def test_item_with_hashtag(self, parser, reducer):
        doc = parser.parse("#ideas\n-item1 { body }")
        reducer.process_document(doc)
        assert "item1" in reducer.state.items
        assert "ideas" in reducer.state.items["item1"].hashtags

    def test_vote_requires_existing_items(self, parser, reducer):
        doc = parser.parse("-item1 10:1 -item2")
        with pytest.raises(ParseError, match="item does not exist"):
            reducer.process_document(doc)

    def test_valid_vote(self, parser, reducer):
        doc = parser.parse("""
#ideas
-item1 { first }
-item2 { second }
-item1 10:1 -item2
""")
        reducer.process_document(doc)
        assert len(reducer.state.votes) == 1
        assert reducer.state.votes[0].item1 == "item1"
        assert reducer.state.votes[0].item2 == "item2"

    def test_vote_with_attribute_context(self, parser, reducer):
        doc = parser.parse("""
#ideas
-item1 { first }
-item2 { second }
:difficulty
-item1 10:1 -item2
""")
        reducer.process_document(doc)
        vote = reducer.state.votes[0]
        assert vote.attribute == "difficulty"

    def test_multiple_hashtags_per_item(self, parser, reducer):
        # First document: item under #ideas
        doc1 = parser.parse("#ideas\n-item1 { body }")
        reducer.process_document(doc1)

        # Second document: same item under #work
        doc2 = parser.parse("#work\n-item1")
        reducer.process_document(doc2)

        item = reducer.state.items["item1"]
        assert "ideas" in item.hashtags
        assert "work" in item.hashtags


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_full_submission_workflow(self, parser, reducer):
        # User submits items
        email1 = """
#tasks
-write-docs { Write documentation for the API }
-fix-bug { Fix the memory leak in parser }
-add-tests { Add comprehensive test coverage }
"""
        doc1 = parser.parse(email1)
        reducer.process_document(doc1, timestamp="2024-01-01")

        # User votes on difficulty
        email2 = """
#tasks
:difficulty
-fix-bug 10:1 -write-docs { Debugging is much harder }
-add-tests 5:1 -write-docs
-fix-bug 2:1 -add-tests
"""
        doc2 = parser.parse(email2)
        reducer.process_document(doc2, timestamp="2024-01-02")

        # Verify state
        assert len(reducer.state.items) == 3
        assert len(reducer.state.votes) == 3

        # All votes should be about difficulty
        for vote in reducer.state.votes:
            assert vote.attribute == "difficulty"

        # Check specific vote
        bug_vs_docs = [
            v for v in reducer.state.votes if v.item1 == "fix-bug" and v.item2 == "write-docs"
        ][0]
        assert bug_vs_docs.ratio_left == 10
        assert bug_vs_docs.ratio_right == 1
        assert "Debugging" in bug_vs_docs.explanation

    def test_c_code_in_body(self, parser):
        text = """
#code-snippets
-quicksort {{
void quicksort(int arr[], int low, int high) {
    if (low < high) {
        int pi = partition(arr, low, high);
        quicksort(arr, low, pi - 1);
    }
}
}}
"""
        doc = parser.parse(text)
        item = [s for s in doc.statements if isinstance(s, Item)][0]
        assert "void quicksort" in item.body
        assert "{" in item.body
        assert "}" in item.body


class TestEdgeCases:
    """Test edge cases and corner scenarios."""

    def test_simple_less_than(self, parser):
        doc = parser.parse("-item1 < -item2")
        vote = doc.statements[0]
        # < means item2 is clearly better (2:1 ratio)
        assert vote.ratio_left == 1
        assert vote.ratio_right == 2

    def test_simple_equal(self, parser):
        doc = parser.parse("-item1 = -item2")
        vote = doc.statements[0]
        # = means equal preference
        assert vote.ratio_left == 1
        assert vote.ratio_right == 1

    def test_zero_ratio_rejected(self, parser, reducer):
        # Zero ratios break the random walk algorithm
        doc = parser.parse("""
#ideas
-a { first }
-b { second }
-a 0:1 -b
""")
        with pytest.raises(ParseError, match="cannot contain 0"):
            reducer.process_document(doc)

    def test_attribute_persists_across_votes(self, parser, reducer):
        doc = parser.parse("""
#ideas
-a { first }
-b { second }
:difficulty
-a > -b
-b > -a
""")
        reducer.process_document(doc)
        # Both votes should have difficulty attribute
        assert len(reducer.state.votes) == 2
        assert reducer.state.votes[0].attribute == "difficulty"
        assert reducer.state.votes[1].attribute == "difficulty"

    def test_multiple_attributes_last_wins(self, parser, reducer):
        doc = parser.parse("""
#ideas
-a { first }
-b { second }
:difficulty :benefit
-a > -b
""")
        reducer.process_document(doc)
        # Vote should have last attribute (benefit)
        assert reducer.state.votes[0].attribute == "benefit"

    def test_user_email_tracking(self, parser, reducer):
        doc = parser.parse("""
#ideas
-item1 { first }
-item2 { second }
-item1 > -item2
""")
        reducer.process_document(doc, timestamp="2024-01-01", user_email="alice@example.com")

        # Check item has created_by
        assert reducer.state.items["item1"].created_by == "alice@example.com"
        assert reducer.state.items["item2"].created_by == "alice@example.com"

        # Check vote has user_email
        assert reducer.state.votes[0].user_email == "alice@example.com"

    def test_same_user_votes_multiple_times(self, parser, reducer):
        # User can vote multiple times (not an error)
        doc = parser.parse("""
#ideas
-a { first }
-b { second }
-a > -b
-a > -b
""")
        reducer.process_document(doc, user_email="alice@example.com")

        # Should have 2 votes from same user
        assert len(reducer.state.votes) == 2
        assert all(v.user_email == "alice@example.com" for v in reducer.state.votes)
