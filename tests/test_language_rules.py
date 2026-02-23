from rules.language import language_guess_is_correct


def test_persian_farsi_compound_label_accepts_both():
    langs = ["Persian (Farsi)"]
    assert language_guess_is_correct("persian", langs)
    assert language_guess_is_correct("farsi", langs)