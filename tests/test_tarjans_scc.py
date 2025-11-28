"""
Comprehensive tests for Tarjan's Strongly Connected Components algorithm.

Tests cover various graph topologies to ensure correct SCC detection.
"""

import numpy as np
import pytest
from src.rank import tarjans_scc


class TestTarjansSCC:
    """Test Tarjan's SCC algorithm on various graph topologies."""

    def test_single_node(self):
        """Single node forms its own component."""
        A = np.array([[0]])
        components = tarjans_scc(A)
        assert len(components) == 1
        assert components[0] == [0]

    def test_two_nodes_connected(self):
        """Two nodes with edges in both directions form one component."""
        A = np.array([
            [0, 1],
            [1, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 1
        assert set(components[0]) == {0, 1}

    def test_two_nodes_one_direction(self):
        """Two nodes with only one direction form separate components."""
        A = np.array([
            [0, 1],
            [0, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 2
        # Each node is its own component
        component_sets = [set(c) for c in components]
        assert {0} in component_sets
        assert {1} in component_sets

    def test_three_nodes_fully_connected(self):
        """Three nodes forming a cycle are one component."""
        A = np.array([
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 1
        assert set(components[0]) == {0, 1, 2}

    def test_three_nodes_chain(self):
        """Three nodes in a chain (no cycle) form separate components."""
        # 0 -> 1 -> 2
        A = np.array([
            [0, 1, 0],
            [0, 0, 1],
            [0, 0, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 3
        # Each node is its own component when there's no cycle
        component_sets = [set(c) for c in components]
        assert {0} in component_sets
        assert {1} in component_sets
        assert {2} in component_sets

    def test_two_separate_pairs(self):
        """Two separate pairs of connected nodes form two components."""
        # (0 <-> 1) and (2 <-> 3), no connection between pairs
        A = np.array([
            [0, 1, 0, 0],
            [1, 0, 0, 0],
            [0, 0, 0, 1],
            [0, 0, 1, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 2
        component_sets = [set(c) for c in components]
        assert {0, 1} in component_sets
        assert {2, 3} in component_sets

    def test_disconnected_singleton(self):
        """Disconnected nodes form separate singleton components."""
        # Three nodes with no edges between them
        A = np.zeros((3, 3))
        components = tarjans_scc(A)
        assert len(components) == 3
        component_sets = [set(c) for c in components]
        assert {0} in component_sets
        assert {1} in component_sets
        assert {2} in component_sets

    def test_complex_graph_with_multiple_sccs(self):
        """Complex graph with multiple SCCs."""
        # Graph structure:
        # Component 1: 0 <-> 1 <-> 2 (all connected in cycle)
        # Component 2: 3 -> 4 (one direction only, so separate)
        # Singleton: 5 (no connections)
        A = np.array([
            [0, 1, 0, 0, 0, 0],  # 0 -> 1
            [0, 0, 1, 0, 0, 0],  # 1 -> 2
            [1, 0, 0, 0, 0, 0],  # 2 -> 0 (completes cycle)
            [0, 0, 0, 0, 1, 0],  # 3 -> 4
            [0, 0, 0, 0, 0, 0],  # 4 (no outgoing edges)
            [0, 0, 0, 0, 0, 0],  # 5 (isolated)
        ])
        components = tarjans_scc(A)
        assert len(components) == 4  # {0,1,2}, {3}, {4}, {5}
        component_sets = [set(c) for c in components]
        assert {0, 1, 2} in component_sets
        assert {3} in component_sets
        assert {4} in component_sets
        assert {5} in component_sets

    def test_self_loop_is_component(self):
        """Node with self-loop is still one component."""
        A = np.array([
            [1, 0],
            [0, 1]
        ])
        components = tarjans_scc(A)
        assert len(components) == 2
        component_sets = [set(c) for c in components]
        assert {0} in component_sets
        assert {1} in component_sets

    def test_weighted_edges_detected(self):
        """Weighted edges (values > 1) are still detected correctly."""
        # Two nodes with weighted bidirectional edges
        A = np.array([
            [0, 5.5],
            [3.2, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 1
        assert set(components[0]) == {0, 1}

    def test_large_single_component(self):
        """Larger graph where all nodes are strongly connected."""
        # Create a cycle through all nodes: 0->1->2->3->4->0
        n = 5
        A = np.zeros((n, n))
        for i in range(n):
            A[i, (i + 1) % n] = 1
        components = tarjans_scc(A)
        assert len(components) == 1
        assert set(components[0]) == set(range(n))

    def test_star_topology_not_strongly_connected(self):
        """Star topology (center with edges to all) is not strongly connected."""
        # Node 0 is center with edges TO all others (0 -> 1, 0 -> 2, 0 -> 3)
        # but no edges back
        A = np.array([
            [0, 1, 1, 1],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0]
        ])
        components = tarjans_scc(A)
        # Each node is separate since no cycles exist
        assert len(components) == 4
        component_sets = [set(c) for c in components]
        for i in range(4):
            assert {i} in component_sets

    def test_bidirectional_star_is_strongly_connected(self):
        """Star with bidirectional edges forms one component."""
        # Node 0 is center with edges TO and FROM all others
        A = np.array([
            [0, 1, 1, 1],
            [1, 0, 0, 0],
            [1, 0, 0, 0],
            [1, 0, 0, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 1
        assert set(components[0]) == {0, 1, 2, 3}

    def test_nested_components(self):
        """Graph with nested SCC structure."""
        # Component 1: 0 <-> 1
        # Component 2: 2 <-> 3
        # With edges from component 1 to component 2 (but not back)
        A = np.array([
            [0, 1, 1, 0],  # 0 <-> 1, 0 -> 2
            [1, 0, 0, 0],
            [0, 0, 0, 1],  # 2 <-> 3
            [0, 0, 1, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 2
        component_sets = [set(c) for c in components]
        assert {0, 1} in component_sets
        assert {2, 3} in component_sets


class TestTarjansWithRankingScenarios:
    """Test Tarjan's algorithm in realistic ranking scenarios."""

    def test_fruit_comparison_scenario(self):
        """Items compared on different attributes form separate graphs."""
        # Scenario:
        # #fruit with :taste -> apple, orange, banana compared
        # #fruit with :price -> separate comparisons

        # For a single attribute, if all items compared, one component
        # apple > orange, orange > banana, banana > apple (cycle)
        A = np.array([
            [0, 2, 0],  # apple > orange (2:1)
            [1, 0, 1],  # orange < apple, orange > banana
            [1, 0, 0]   # banana > apple (completes cycle)
        ])
        components = tarjans_scc(A)
        assert len(components) == 1
        assert set(components[0]) == {0, 1, 2}

    def test_disconnected_voting_blocks(self):
        """Two groups of items compared within groups but not between."""
        # Fruit group: 0 <-> 1
        # Veggie group: 2 <-> 3
        # No comparisons between groups
        A = np.array([
            [0, 1, 0, 0],
            [1, 0, 0, 0],
            [0, 0, 0, 1],
            [0, 0, 1, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 2
        component_sets = [set(c) for c in components]
        assert {0, 1} in component_sets
        assert {2, 3} in component_sets

    def test_bridge_vote_connects_groups(self):
        """Single bridge vote connects two otherwise separate groups."""
        # Group 1: 0 <-> 1
        # Group 2: 2 <-> 3
        # Bridge: 1 <-> 2 (bidirectional to form strong connection)
        A = np.array([
            [0, 1, 0, 0],  # 0 <-> 1
            [1, 0, 1, 0],  # 1 <-> 2 (bridge)
            [0, 1, 0, 1],  # 2 <-> 3
            [0, 0, 1, 0]
        ])
        components = tarjans_scc(A)
        # All should be one component due to cycle: 0 -> 1 -> 2 -> 3 -> 2 -> 1 -> 0
        assert len(components) == 1
        assert set(components[0]) == {0, 1, 2, 3}

    def test_unvoted_item_is_singleton(self):
        """Item with no votes forms singleton component."""
        # 0 <-> 1, but 2 has no votes
        A = np.array([
            [0, 1, 0],
            [1, 0, 0],
            [0, 0, 0]
        ])
        components = tarjans_scc(A)
        assert len(components) == 2
        component_sets = [set(c) for c in components]
        assert {0, 1} in component_sets
        assert {2} in component_sets
