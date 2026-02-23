import importlib

def test_record_score_only_updates_if_higher(tmp_path, monkeypatch):
    # Set env var BEFORE importing leaderboard, so module constants are correct
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    import leaderboard
    importlib.reload(leaderboard)  # ensure it picks up DATA_DIR for this test run

    assert leaderboard.record_score("alice", 10) is True
    top = leaderboard.get_top_entries(20)
    assert top[0].name == "alice"
    assert top[0].score == 10

    # lower score should not update
    assert leaderboard.record_score("alice", 8) is False
    top2 = leaderboard.get_top_entries(20)
    assert top2[0].score == 10

    # higher score should update
    assert leaderboard.record_score("alice", 15) is True
    top3 = leaderboard.get_top_entries(20)
    assert top3[0].score == 15