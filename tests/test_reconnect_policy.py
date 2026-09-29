"""Backoff policy for self-healing reconnect.

The policy is pure arithmetic: given how many attempts have already failed, how
long should the bot wait before the next one, and when is it time to give up
and stop hammering the login server? Keeping it pure means the retry schedule
is deterministic in tests — no sleeps, no network.
"""
import pytest

from skua_lite.reconnect import ReconnectPolicy


def test_first_retry_uses_base_delay():
    policy = ReconnectPolicy(base_delay=2.0, factor=2.0, max_delay=60.0, max_attempts=5)
    assert policy.delay_for(attempt=1) == 2.0


def test_delay_grows_exponentially_between_attempts():
    policy = ReconnectPolicy(base_delay=2.0, factor=2.0, max_delay=60.0, max_attempts=5)
    assert [policy.delay_for(n) for n in range(1, 5)] == [2.0, 4.0, 8.0, 16.0]


def test_delay_is_capped_at_max_delay():
    policy = ReconnectPolicy(base_delay=2.0, factor=2.0, max_delay=10.0, max_attempts=8)
    assert policy.delay_for(attempt=6) == 10.0


def test_gives_up_after_max_attempts():
    policy = ReconnectPolicy(base_delay=1.0, factor=2.0, max_delay=30.0, max_attempts=3)
    assert policy.should_retry(attempt=0) is True
    assert policy.should_retry(attempt=2) is True
    assert policy.should_retry(attempt=3) is False


def test_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        ReconnectPolicy(base_delay=0, factor=2.0, max_delay=10.0, max_attempts=3)
    with pytest.raises(ValueError):
        ReconnectPolicy(base_delay=1.0, factor=1.0, max_delay=10.0, max_attempts=3)
    with pytest.raises(ValueError):
        ReconnectPolicy(base_delay=1.0, factor=2.0, max_delay=0.5, max_attempts=3)
    with pytest.raises(ValueError):
        ReconnectPolicy(base_delay=1.0, factor=2.0, max_delay=10.0, max_attempts=0)


def test_negative_attempt_is_treated_as_first():
    policy = ReconnectPolicy(base_delay=3.0, factor=2.0, max_delay=60.0, max_attempts=4)
    assert policy.delay_for(attempt=0) == 3.0
    assert policy.delay_for(attempt=-5) == 3.0
