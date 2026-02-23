from rules.competition import validate_player_name


def test_name_min_letters():
    ok, err = validate_player_name("Al")
    assert not ok
    assert "3 letters" in err

    ok, err = validate_player_name("Abc")
    assert ok


def test_name_allowed_chars():
    ok, err = validate_player_name("Jean-Pierre")
    assert ok

    ok, err = validate_player_name("Bad!!!")
    assert not ok


def test_name_profanity():
    ok, err = validate_player_name("shithead")
    assert not ok