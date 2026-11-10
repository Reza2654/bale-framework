"""Finite State Machine definitions for multi-step bot interactions."""
from __future__ import annotations
from framework.fsm import State, StatesGroup

class AddURLStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_alias = State()
