"""Test cases for line filtering edge cases.

These tests document the limitations of the brace-counting approach
in parse_lines(). See docs/line-filtering-dilemma.md for details.
"""

import pytest

from src.parser import EmailDSLParser


@pytest.fixture
def parser():
    return EmailDSLParser()


class TestLineFilteringEdgeCases:
    """Test edge cases in line filtering with brace depth tracking."""

    def test_simple_filtering_works(self, parser):
        """Line filtering correctly removes email noise."""
        text = """Hi there!

#ideas
/task1 { description }

Sent from my iPhone"""

        doc = parser.parse_lines(text)
        # Should parse hashtag and item, ignore greetings/signature
        assert len(doc.statements) == 2
        assert doc.statements[0].name == "ideas"
        assert doc.statements[1].title == "task1"

    def test_multiline_body_works(self, parser):
        """Line filtering keeps multi-line body content."""
        text = """#ideas
/task1 {
  This is a longer
  description with
  multiple lines
}
/task2"""

        doc = parser.parse_lines(text)
        assert len(doc.statements) == 3
        assert "multiple lines" in doc.statements[1].body

    def test_balanced_braces_in_code_works(self, parser):
        """Balanced braces in code work because they cancel out."""
        text = """#code
/snippet {{
  printf("{test}");
}}"""

        doc = parser.parse_lines(text)
        assert len(doc.statements) == 2
        assert '"{test}"' in doc.statements[1].body

    def test_double_braces_with_nested_works(self, parser):
        """Double braces with nested braces work if balanced per line."""
        text = """#code
/snippet {{
  code with { nested } braces
}}"""

        doc = parser.parse_lines(text)
        assert len(doc.statements) == 2
        assert "{ nested }" in doc.statements[1].body

    def test_unbalanced_brace_in_string_now_works(self, parser):
        """FIXED: Masking approach handles unbalanced braces in strings.

        The old brace-counting approach failed here, but the new masking
        approach correctly protects the body content before filtering.
        """
        text = """#code
/snippet {{
  printf("{test");
}}
This should be noise
/item2"""

        # This now WORKS! Masking protects the body, filters noise
        doc = parser.parse_lines(text)
        assert len(doc.statements) == 3  # hashtag, snippet, item2
        assert doc.statements[1].body  # Body is preserved
        assert 'printf' in doc.statements[1].body

    def test_unbalanced_brace_in_comment_now_works(self, parser):
        """FIXED: Masking approach handles unbalanced braces in comments."""
        text = """#code
/snippet {{
  // Comment with opening brace: {
  return 0;
}}
Noise after"""

        # This now WORKS too!
        doc = parser.parse_lines(text)
        assert len(doc.statements) == 2  # hashtag, snippet
        assert '// Comment' in doc.statements[1].body

    def test_no_noise_after_unbalanced_works(self, parser):
        """Even with unbalanced braces, works if no noise follows.

        The depth tracking is wrong, but since there's nothing after
        the body, the parser doesn't encounter the problematic lines.
        """
        text = """#code
/snippet {{
  printf("{test");
}}"""

        # This works! Even though depth tracking is wrong, there's no
        # noise after the body to cause problems
        doc = parser.parse_lines(text)
        assert len(doc.statements) == 2

    def test_parse_without_filtering_always_works(self, parser):
        """Using parse() instead of parse_lines() avoids the issue.

        This works because we're not using line filtering at all.
        The full grammar handles the structure correctly.
        """
        text = """#code
/snippet {{
  printf("{test");
}}
/item2"""

        # parse() works fine (no line filtering)
        doc = parser.parse(text)
        assert len(doc.statements) == 3

    def test_workaround_balanced_braces(self, parser):
        """WORKAROUND: Balance braces in string literals."""
        text = """#code
/snippet {{
  printf("{test}");  // Closing brace added
}}
Noise after
/item2"""

        # Works because braces are balanced: +1-1=0 on the printf line
        doc = parser.parse_lines(text)
        assert len(doc.statements) == 3

    def test_workaround_noise_before_dsl(self, parser):
        """WORKAROUND: Put noise before DSL commands, not after."""
        text = """Hi there!

#code
/snippet {{
  printf("{test");
}}"""

        # Works because noise is filtered at the start, before any braces
        doc = parser.parse_lines(text)
        assert len(doc.statements) == 2


class TestBraceDepthTracking:
    """Direct tests of the brace depth tracking logic."""

    def test_depth_tracking_simple(self):
        """Test basic depth tracking logic."""
        lines = ["#test", "/item {", "body", "}"]
        depths = []
        depth = 0

        for line in lines:
            open_b = line.count("{")
            close_b = line.count("}")
            depths.append(depth)
            depth = max(0, depth + open_b - close_b)

        assert depths == [0, 0, 1, 1]  # depth before processing each line
        assert depth == 0  # final depth

    def test_depth_tracking_with_unbalanced_string(self):
        """Show how unbalanced braces in strings break depth tracking."""
        lines = [
            "#test",
            '/item {{',
            '  printf("{test");',  # Has unbalanced opening brace!
            '  printf("{test");',  # Another one
        ]

        depth = 0
        for i, line in enumerate(lines):
            open_b = line.count("{")
            close_b = line.count("}")
            depth = max(0, depth + open_b - close_b)

        # Depth is wrong! Should be 2 (from {{) but is 4 (counted string braces)
        assert depth == 4  # This is the BUG - we want 2 but get 4

    def test_depth_tracking_fails_with_unbalanced(self):
        """Show exact failure case."""
        lines = [
            "#test",
            '/item {{',           # depth 0 → 2
            '  printf("{test");', # depth 2 → 3 (WRONG! Should stay 2)
            '}}',                 # depth 3 → 1 (WRONG! Should be 0)
            'Noise',              # depth=1, so this gets KEPT
        ]

        depth = 0
        depths_after = []
        for line in lines:
            open_b = line.count("{")
            close_b = line.count("}")
            depth = max(0, depth + open_b - close_b)
            depths_after.append(depth)

        assert depths_after == [0, 2, 3, 1, 1]
        # The problem: final depth is 1, not 0!
        # This means the "Noise" line gets kept when it shouldn't be


class TestAlternativeApproaches:
    """Test alternative approaches to the filtering problem."""

    def test_no_filtering_requires_clean_input(self, parser):
        """Without filtering, noise causes parse failures."""
        text = """Hi there!
#ideas
/task1"""

        # This fails because "Hi there!" is not valid DSL
        with pytest.raises(Exception):
            parser.parse(text)

    def test_filtering_only_start_and_end(self, parser):
        """Alternative: Filter only lines before first DSL and after last DSL.

        This approach doesn't solve the fundamental issue - even if we keep
        all lines between first and last DSL, the grammar still can't parse
        unbalanced braces in single-brace bodies. Need double braces for that.
        """
        text = """Hi there!

#ideas
/task1 {{
  printf("{test");
}}

Sent from my iPhone"""

        # Manual filtering: keep lines from first # to last }
        lines = text.split("\n")
        start = next(i for i, line in enumerate(lines) if line.strip().startswith("#"))
        end = len(lines) - next(i for i, line in enumerate(reversed(lines)) if "}" in line)

        filtered = "\n".join(lines[start:end])
        doc = parser.parse(filtered)

        # This works with double braces {{}} which allow nested content
        assert len(doc.statements) == 2
