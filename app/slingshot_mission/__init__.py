"""SLINGSHOT mission package — multi-agent planetary-defense mission control.

Exports:
  root_agent        — CAPCOM dispatcher + 5 specialist sub-agents (agent.py)
  log_ai_interaction— server-side transcript helper for main.py (tools.py)
"""
from .agent import root_agent, log_ai_interaction

__all__ = ["root_agent", "log_ai_interaction"]
