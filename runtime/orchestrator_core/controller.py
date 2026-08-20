"""Stable pure-controller facade used by adapters and tests."""

from .events import apply_event
from .model import new_state as create_state
from .routing import reserve_next

__all__ = ["apply_event", "create_state", "reserve_next"]
