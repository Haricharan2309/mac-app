"""Reconnect backoff: exponential growth, a ceiling, a finite attempt budget,
and a reset after a good connection.
"""

from aria.backoff import Backoff


def test_exponential_growth_and_cap():
    b = Backoff(base=1, factor=2, cap=10, max_attempts=10)
    assert [b.next() for _ in range(6)] == [1, 2, 4, 8, 10, 10]


def test_attempt_budget_exhausts_to_none():
    b = Backoff(base=1, factor=2, cap=100, max_attempts=3)
    assert b.next() == 1
    assert b.next() == 2
    assert b.next() == 4
    assert b.next() is None  # budget spent


def test_reset_restarts_the_sequence():
    b = Backoff(base=1, factor=2, cap=100, max_attempts=3)
    b.next()
    b.next()
    b.reset()
    assert b.next() == 1
