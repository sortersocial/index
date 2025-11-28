"""
Integration tests for disconnected component detection and ranking.

Tests the full flow from parsing to ranking with attribute slicing and
disconnected graph topology.
"""

import pytest
from src.parser import EmailDSLParser
from src.reducer import Reducer, ParseError
from src.rank import compute_rankings_from_state


class TestDisconnectedComponents:
    """Test ranking with disconnected components."""

    def test_single_component_all_connected(self):
        """When all items are compared, single component is formed."""
        content = """
#fruit
:taste
/apple
/orange
/banana

/apple > /orange
/orange > /banana
/banana > /apple
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="fruit",
            attribute="taste"
        )

        # All items should be in component 0
        assert len(rankings) == 3
        assert all(comp_id == 0 for _, _, _, comp_id in rankings)

    def test_two_disconnected_components(self):
        """Two groups of items with no cross-comparison form separate components."""
        content = """
#food
:taste
/apple
/orange
/carrot
/celery

/apple > /orange

/carrot > /celery
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="food",
            attribute="taste"
        )

        # Should have 4 items in 2 components
        assert len(rankings) == 4
        component_ids = [comp_id for _, _, _, comp_id in rankings]
        assert len(set(component_ids)) == 2

        # Check that apple and orange are in same component
        apple_comp = next(comp for title, _, _, comp in rankings if title == "apple")
        orange_comp = next(comp for title, _, _, comp in rankings if title == "orange")
        assert apple_comp == orange_comp

        # Check that carrot and celery are in same component
        carrot_comp = next(comp for title, _, _, comp in rankings if title == "carrot")
        celery_comp = next(comp for title, _, _, comp in rankings if title == "celery")
        assert carrot_comp == celery_comp

        # Check that fruit and veggie groups are in different components
        assert apple_comp != carrot_comp

    def test_singleton_unvoted_item(self):
        """Item with no votes forms singleton component."""
        content = """
#fruit
:taste
/apple
/orange
/banana

/apple > /orange
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="fruit",
            attribute="taste"
        )

        # Should have 3 items: 2 in one component, 1 singleton
        assert len(rankings) == 3
        component_ids = [comp_id for _, _, _, comp_id in rankings]
        assert len(set(component_ids)) == 2

        # Banana should be in its own component
        banana_items = [(title, comp) for title, _, _, comp in rankings if title == "banana"]
        assert len(banana_items) == 1
        banana_comp = banana_items[0][1]

        # Apple and orange should share a component different from banana
        apple_comp = next(comp for title, _, _, comp in rankings if title == "apple")
        orange_comp = next(comp for title, _, _, comp in rankings if title == "orange")
        assert apple_comp == orange_comp
        assert apple_comp != banana_comp

    def test_bridge_vote_merges_components(self):
        """Adding a bridge vote connects previously disconnected groups."""
        content = """
#food
:taste
/apple
/orange
/carrot
/celery

/apple > /orange
/carrot > /celery

/orange > /carrot
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="food",
            attribute="taste"
        )

        # All items should now be in single component due to bridge
        assert len(rankings) == 4
        component_ids = [comp_id for _, _, _, comp_id in rankings]
        assert len(set(component_ids)) == 1

    def test_multiple_singleton_components(self):
        """Multiple items with no votes form separate singleton components."""
        content = """
#fruit
:taste
/apple
/orange
/banana
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="fruit",
            attribute="taste"
        )

        # All items are singletons
        assert len(rankings) == 3
        component_ids = [comp_id for _, _, _, comp_id in rankings]
        assert len(set(component_ids)) == 3

        # Each item should have rank 1 within its component
        for _, _, rank, _ in rankings:
            assert rank == 1


class TestAttributeSlicing:
    """Test that different attributes create separate ranking spaces."""

    def test_different_attributes_separate_rankings(self):
        """Same items compared on different attributes form separate rankings."""
        content = """
#ideas
/idea1
/idea2
/idea3

:impact
/idea1 > /idea2
/idea2 > /idea3

:feasibility
/idea3 > /idea1
/idea1 > /idea2
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        # Get rankings for impact
        impact_rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="ideas",
            attribute="impact"
        )

        # Get rankings for feasibility
        feasibility_rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="ideas",
            attribute="feasibility"
        )

        # Both should have all 3 items
        assert len(impact_rankings) == 3
        assert len(feasibility_rankings) == 3

        # Rankings should be different
        impact_order = [title for title, _, _, _ in impact_rankings]
        feasibility_order = [title for title, _, _, _ in feasibility_rankings]
        assert impact_order != feasibility_order

    def test_attribute_without_votes_returns_unranked(self):
        """Querying attribute with no votes returns unranked items."""
        content = """
#ideas
/idea1
/idea2

:impact
/idea1 > /idea2
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        # Query for non-existent attribute
        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="ideas",
            attribute="feasibility"
        )

        # Should return items unranked
        assert len(rankings) == 2
        for _, _, rank, _ in rankings:
            assert rank == 1

    def test_vote_without_attribute_raises_error(self):
        """Voting without attribute context raises ParseError."""
        content = """
#fruit
/apple
/orange

/apple > /orange
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        with pytest.raises(ParseError, match="attribute context"):
            reducer.process_document(doc, timestamp="0", user_email="test@example.com")


class TestHashtagFiltering:
    """Test that hashtags create separate ranking spaces."""

    def test_different_hashtags_separate_rankings(self):
        """Items in different hashtags are ranked separately."""
        content = """
#fruit
/apple
/orange

:taste
/apple > /orange

#veggies
/carrot
/celery

:taste
/carrot > /celery
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        # Get fruit rankings
        fruit_rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="fruit",
            attribute="taste"
        )

        # Get veggie rankings
        veggie_rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="veggies",
            attribute="taste"
        )

        # Fruit should only have fruit items
        assert len(fruit_rankings) == 2
        fruit_titles = {title for title, _, _, _ in fruit_rankings}
        assert fruit_titles == {"apple", "orange"}

        # Veggies should only have veggie items
        assert len(veggie_rankings) == 2
        veggie_titles = {title for title, _, _, _ in veggie_rankings}
        assert veggie_titles == {"carrot", "celery"}

    def test_item_in_multiple_hashtags(self):
        """Item can appear in multiple hashtags and be ranked separately."""
        content = """
#food
/tomato
/potato

:taste
/tomato > /potato

#fruit
/tomato
/apple

:taste
/apple > /tomato
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        # Get food rankings
        food_rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="food",
            attribute="taste"
        )

        # Get fruit rankings
        fruit_rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="fruit",
            attribute="taste"
        )

        # Tomato should appear in both rankings
        food_titles = {title for title, _, _, _ in food_rankings}
        fruit_titles = {title for title, _, _, _ in fruit_rankings}
        assert "tomato" in food_titles
        assert "tomato" in fruit_titles

        # Rankings should be different (different comparison sets)
        assert len(food_rankings) == 2
        assert len(fruit_rankings) == 2

    def test_hashtag_not_found_returns_empty(self):
        """Querying non-existent hashtag returns empty results."""
        content = """
#fruit
/apple

:taste
/apple > /apple
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="nonexistent",
            attribute="taste"
        )

        assert rankings == []


class TestRankingWithinComponents:
    """Test that items are ranked correctly within their components."""

    def test_ranks_within_component_correct(self):
        """Items within same component have correct relative ranks."""
        content = """
#fruit
:taste
/apple
/orange
/banana
/grape

/apple 3:1 /orange
/orange 2:1 /banana
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="fruit",
            attribute="taste"
        )

        # Apple, orange, and banana should all be in one component
        # (comparisons create bidirectional edges, forming SCC)
        # Grape should be singleton (no votes)
        apple_data = next((title, rank, comp) for title, _, rank, comp in rankings if title == "apple")
        orange_data = next((title, rank, comp) for title, _, rank, comp in rankings if title == "orange")
        banana_data = next((title, rank, comp) for title, _, rank, comp in rankings if title == "banana")
        grape_data = next((title, rank, comp) for title, _, rank, comp in rankings if title == "grape")

        # Apple should rank higher than orange (3:1 ratio)
        assert apple_data[1] < orange_data[1]  # Lower rank number = better

        # Apple, orange, and banana should all be in same component
        # (bidirectional edges from comparisons form SCC)
        assert apple_data[2] == orange_data[2]
        assert orange_data[2] == banana_data[2]

        # Grape should be in different component (no votes)
        assert grape_data[2] != apple_data[2]

    def test_component_ids_are_distinct(self):
        """Each component gets a unique ID."""
        content = """
#food
:taste
/a
/b
/c
/d

/a > /b
/c > /d
        """
        parser = EmailDSLParser()
        doc = parser.parse_lines(content)

        reducer = Reducer()
        reducer.process_document(doc, timestamp="0", user_email="test@example.com")

        rankings = compute_rankings_from_state(
            reducer.state,
            hashtag="food",
            attribute="taste"
        )

        component_ids = [comp_id for _, _, _, comp_id in rankings]
        unique_components = set(component_ids)

        # Should have exactly 2 unique component IDs
        assert len(unique_components) == 2
