"""
Shared mutable state for NoApiBot.
Isolated to prevent circular imports between modules.
"""
import asyncio

from noapibot.config import DEFAULT_MODEL, DEFAULT_ENGINE

# ─── Runtime State ────────────────────────────────────
current_model = DEFAULT_MODEL
current_engine = DEFAULT_ENGINE
active_skills = []  # list of loaded skill names

# ─── Rate Limiter ─────────────────────────────────────
mcp_semaphore = asyncio.Semaphore(1)
last_mcp_request_time = 0.0

# ─── Bot App Reference ───────────────────────────────
bot_app = None  # Set in main()
