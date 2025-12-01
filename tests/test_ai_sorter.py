"""Test rig for AI todo sorter."""
import pytest
from src.todo import storage, ai_voter
from src.rank import compute_rankings_from_state


def test_create_todo_list():
    """Test creating a basic todo list."""
    items = [
        "Write tests for AI sorter",
        "Implement SSE streaming",
        "Add Datastar UI",
        "Deploy to production",
        "Write documentation"
    ]

    list_id = storage.create_todo_list(
        items=items,
        criteria="urgency",
        model="anthropic/claude-3.5-haiku"
    )

    assert list_id is not None
    assert len(list_id) == 8  # UUID hex[:8]

    # Verify file was created
    file_path = storage.get_file_path(list_id)
    assert file_path.exists()

    # Verify we can read it back
    state, meta = storage.get_todo_state(list_id)
    assert state is not None
    assert meta["criteria"] == "urgency"
    assert meta["model"] == "anthropic/claude-3.5-haiku"
    assert len(state.items) == 5

    print(f"\n✓ Created todo list: {list_id}")
    print(f"  File: {file_path}")
    print(f"  Items: {list(state.items.keys())}")

    return list_id


def test_append_vote():
    """Test appending a manual vote."""
    items = ["Task A", "Task B", "Task C"]
    list_id = storage.create_todo_list(items, "importance", "test-model")

    # Append a manual vote (use slugified names)
    storage.append_vote(list_id, "/task-a > /task-b { A is more important }")

    # Verify it was added
    state, _ = storage.get_todo_state(list_id)
    assert len(state.votes) == 1
    assert state.votes[0].item1 == "task-a"
    assert state.votes[0].item2 == "task-b"

    print(f"\n✓ Appended vote to {list_id}")


@pytest.mark.skipif(
    not storage.TODO_DIR.exists(),
    reason="Todo directory not initialized"
)
def test_ai_voting_full_flow():
    """Full integration test: create list → AI votes → check rankings.

    This test actually calls the OpenRouter API, so it requires:
    - OPENROUTER_API_KEY environment variable
    - Internet connection
    """
    import os
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")

    print("\n" + "="*60)
    print("AI SORTER FULL FLOW TEST")
    print("="*60)

    # Create a todo list
    items = [
        "Fix critical bug in production",
        "Refactor legacy code",
        "Write documentation",
        "Add new feature request",
        "Update dependencies"
    ]

    list_id = storage.create_todo_list(
        items=items,
        criteria="urgency",
        model="anthropic/claude-3.5-haiku"
    )

    print(f"\n📋 Created list: {list_id}")
    print(f"Criteria: urgency")
    print(f"Items: {len(items)}")

    # Get initial rankings (all equal)
    state, meta = storage.get_todo_state(list_id)
    initial_rankings = compute_rankings_from_state(state, f"todo-{list_id}", "urgency")

    print("\n📊 Initial rankings (no votes):")
    for title, score, rank, _ in initial_rankings:
        print(f"  #{rank} {title:40} (score: {score:.4f})")

    # Run AI sorting
    print(f"\n🤖 Running AI voting (5 comparisons)...")
    print("-" * 60)

    vote_results = ai_voter.run_ai_sorting(list_id, num_votes=5)

    print("-" * 60)
    print(f"\n✓ Completed {len([v for v in vote_results if v['dsl']])} successful votes")

    # Get updated rankings
    state, _ = storage.get_todo_state(list_id)
    final_rankings = compute_rankings_from_state(state, f"todo-{list_id}", "urgency")

    print("\n📊 Final rankings (after AI voting):")
    for title, score, rank, _ in final_rankings:
        print(f"  #{rank} {title:40} (score: {score:.4f})")

    # Print vote log
    print("\n📝 Vote log:")
    for i, vote in enumerate(vote_results, 1):
        if vote['dsl']:
            print(f"  {i}. {vote['item1']} vs {vote['item2']}")
            print(f"     → {vote['reason']}")
        else:
            print(f"  {i}. {vote['item1']} vs {vote['item2']} → FAILED")

    # Print the actual .sorter file for inspection
    file_path = storage.get_file_path(list_id)
    print(f"\n📄 File contents ({file_path}):")
    print("-" * 60)
    print(file_path.read_text())
    print("-" * 60)

    # Assertions
    assert len(state.votes) > 0, "Should have at least one vote"
    assert len(final_rankings) == len(items), "Should rank all items"

    # Check that rankings actually changed (scores should differ)
    scores = [score for _, score, _, _ in final_rankings]
    assert len(set(scores)) > 1, "Scores should vary after voting"

    print(f"\n✅ Test passed!")
    return list_id


if __name__ == "__main__":
    # Run tests directly for quick iteration
    print("Running AI Sorter Test Rig\n")

    try:
        test_create_todo_list()
        test_append_vote()
        test_ai_voting_full_flow()
        print("\n" + "="*60)
        print("ALL TESTS PASSED ✅")
        print("="*60)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
