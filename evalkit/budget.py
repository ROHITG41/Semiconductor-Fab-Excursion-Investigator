"""budget.py - count and throttle model calls so a batch never runs past a free-tier allowance.

BudgetExceeded derives from BaseException on purpose: the agent code has broad `except Exception` fallbacks
(for example when structured output fails). A budget stop must not be swallowed by them.
"""
from __future__ import annotations

import threading
import time


class BudgetExceeded(BaseException):
    pass


class CallBudget:
    """Counts calls made by OUR code to the chat model. The Google client may retry internally on 429/5xx,
    so real HTTP requests can be higher than this count; embeddings are counted separately by Google."""

    def __init__(self, max_calls: int, min_interval_s: float = 0.0, sleep=time.sleep, clock=time.monotonic):
        self.max_calls = int(max_calls)
        self.min_interval_s = float(min_interval_s)
        self.used = 0
        self._last = None
        self._lock = threading.Lock()
        self._sleep, self._clock = sleep, clock

    def charge(self) -> None:
        with self._lock:
            if self.used >= self.max_calls:
                raise BudgetExceeded(f"call budget of {self.max_calls} reached")
            if self._last is not None and self.min_interval_s > 0:
                wait = self.min_interval_s - (self._clock() - self._last)
                if wait > 0:
                    self._sleep(wait)
            self._last = self._clock()
            self.used += 1


class CountingModel:
    """Proxy around a chat model (or a bound / structured-output version of it). Every invoke is charged."""

    def __init__(self, inner, budget: CallBudget):
        self._inner, self._budget = inner, budget

    def invoke(self, *args, **kwargs):
        self._budget.charge()
        return self._inner.invoke(*args, **kwargs)

    def bind_tools(self, *args, **kwargs):
        return CountingModel(self._inner.bind_tools(*args, **kwargs), self._budget)

    def with_structured_output(self, *args, **kwargs):
        return CountingModel(self._inner.with_structured_output(*args, **kwargs), self._budget)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def wrapper_for(budget: CallBudget):
    return lambda model: CountingModel(model, budget)
