"""Concierge Brain — central orchestrator.

Routes reactive (user messages) and proactive (cron-triggered) paths.
Gathers context, calls LLM, applies safety checks, and dispatches responses.
"""
