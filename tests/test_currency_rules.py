from rules.currency import currency_guess_is_correct

def test_dollar_defaults_to_usd():
    assert currency_guess_is_correct(
        "dollar",
        [{"code": "USD", "name": "United States dollar", "symbol": "$"}]
    )

def test_dollar_not_accepted_for_aud():
    assert not currency_guess_is_correct(
        "dollar",
        [{"code": "AUD", "name": "Australian dollar", "symbol": "$"}]
    )