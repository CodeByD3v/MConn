from mconn_receiver.api.rate_limit import FixedWindowLimiter


def test_limiter_rejects_after_limit_and_recovers_after_window():
    limiter = FixedWindowLimiter(limit=2, window_seconds=60)
    assert limiter.allow("192.168.1.10", now=0)
    assert limiter.allow("192.168.1.10", now=1)
    assert not limiter.allow("192.168.1.10", now=2)
    assert limiter.allow("192.168.1.10", now=61)


def test_limiter_keeps_source_ips_separate():
    limiter = FixedWindowLimiter(limit=1, window_seconds=60)
    assert limiter.allow("192.168.1.10", now=0)
    assert limiter.allow("192.168.1.11", now=0)
