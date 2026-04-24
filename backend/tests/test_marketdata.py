from app.marketdata.feed import SyntheticFeed


def test_feed_is_deterministic_per_bot_symbol():
    f1 = SyntheticFeed("bot_1")
    f2 = SyntheticFeed("bot_1")
    p1 = [f1.next_bar("EUR/USD").close for _ in range(20)]
    p2 = [f2.next_bar("EUR/USD").close for _ in range(20)]
    assert p1 == p2  # same bot+symbol → identical sequence


def test_feed_diverges_across_bots():
    f1 = SyntheticFeed("bot_a")
    f2 = SyntheticFeed("bot_b")
    p1 = [f1.next_bar("EUR/USD").close for _ in range(20)]
    p2 = [f2.next_bar("EUR/USD").close for _ in range(20)]
    assert p1 != p2


def test_warm_up_pre_fills_history():
    f = SyntheticFeed("bot_w")
    f.warm_up("EUR/USD", n=25)
    assert len(f.history("EUR/USD")) == 25
