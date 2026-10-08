from webhooks.services.retry_policy import RetryPolicy

POLICY = RetryPolicy(max_attempts=5, base_seconds=10, max_seconds=60)


def test_the_window_doubles_on_every_attempt():
    assert POLICY.delay_after(1, rng=lambda: 1.0) == 10
    assert POLICY.delay_after(2, rng=lambda: 1.0) == 20
    assert POLICY.delay_after(3, rng=lambda: 1.0) == 40


def test_the_window_is_capped():
    assert POLICY.delay_after(4, rng=lambda: 1.0) == 60


def test_jitter_keeps_at_least_half_of_the_window():
    assert POLICY.delay_after(2, rng=lambda: 0.0) == 10


def test_gives_up_after_the_last_attempt():
    assert POLICY.delay_after(5) is None
