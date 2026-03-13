"""
Advanced handlers: /auto, /ralphW, /engine, /claude, /gemini, /mcp, /mcps,
usage monitoring, and auto-refresh.
"""
import re
import json
import asyncio
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from noapibot.config import SKILLS_DIR, ANTIGRAVITY_MODELS
from noapibot.memory import load_memory, save_memory
from noapibot.core import run_opencode, run_with_context, send_response
from noapibot.websocket import broadcast_status
import noapibot.state as state
import noapibot.memory as memory_mod


# ─── MCP Commands ─────────────────────────────────────

async def mcp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: /mcp <servidor> <herramienta> [args_en_json]\n"
            'Ejemplo: `/mcp sqlite read_query {"query": "SELECT 1"}`',
            parse_mode="Markdown"
        )
        return
    from noapibot.handlers.skills import run_skill_script
    await run_skill_script(update, context, "mcp-client/scripts/mcp_execute.py", context.args,
                          f"Ejecutando MCP: {context.args[0]} -> {context.args[1]}")


async def mcps_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    servers_file = SKILLS_DIR / "mcp-client" / "servers.json"
    if not servers_file.exists():
        await update.message.reply_text("❌ No se encontró `servers.json` en la carpeta mcp-client.")
        return
    try:
        servers = json.loads(servers_file.read_text(encoding="utf-8"))
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo servers.json: {e}")
        return
    msg = "🔌 **Servidores MCP Configurados**\n\n"
    for name in servers:
        msg += f"  🔹 `{name}`\n"
    msg += "\nUsa: `/mcp <server> <tool> <args>`"
    await update.message.reply_text(msg, parse_mode="Markdown")


# ─── Engine / CLI Commands ───────────────────────────

async def engine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            f"⚙️ Engine actual: `{state.current_engine}`\n\n"
            "Opciones:\n/engine opencode\n/engine api\n/engine claude\n/engine gemini"
        )
        return
    engine = context.args[0].lower()
    if engine not in ("opencode", "api", "claude", "gemini"):
        await update.message.reply_text("❌ Engines válidos: opencode, api, claude, gemini")
        return
    state.current_engine = engine
    await update.message.reply_text(f"✔️ Engine cambiado a: `{engine}`")


async def claude_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /claude <prompt>")
        return
    prompt = " ".join(context.args)
    s = await update.message.reply_text("🔵 Claude procesando...")
    try:
        result = await run_opencode(state.current_model, prompt, engine_override="claude")
        await send_response(update, s, result)
    except Exception as e:
        await s.edit_text(f"❌ {e}")


async def gemini_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /gemini <prompt>")
        return
    prompt = " ".join(context.args)
    s = await update.message.reply_text("🟡 Gemini CLI procesando...")
    try:
        result = await run_opencode(state.current_model, prompt, engine_override="gemini")
        await send_response(update, s, result)
    except Exception as e:
        await s.edit_text(f"❌ {e}")


# ─── Auto Mode ────────────────────────────────────────

async def auto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Autonomous agent mode with pre-planning."""
    if not context.args:
        await update.message.reply_text("Uso: /auto <instrucción completa>")
        return
    instruction = " ".join(context.args)
    status = await update.message.reply_text("🤖 Modo Autónomo activado. Planificando...")

    thread_id = getattr(update.message, 'message_thread_id', None)
    session_id = f"topic_{thread_id}" if getattr(update.message, 'is_topic_message', False) and thread_id else memory_mod.current_session

    plan_prompt = (
        f"El usuario quiere que trabajes en modo autónomo. Tu tarea: {instruction}\n\n"
        "ANTES de ejecutar, crea un plan breve (3-5 pasos) y luego ejecútalo paso a paso usando tus herramientas."
    )

    try:
        result = await run_with_context(
            state.current_model, plan_prompt, session_id=session_id,
            chat_id=update.effective_chat.id, thread_id=thread_id, max_depth=5
        )
        memory = load_memory(session_id)
        memory.append({"role": "user", "text": f"/auto {instruction}", "ts": datetime.now().isoformat()})
        memory.append({"role": "assistant", "text": result, "ts": datetime.now().isoformat()})
        save_memory(memory, session_id)
        await send_response(update, status, result)
        await broadcast_status("idle", "", agent="NoApiBot")
    except Exception as e:
        await status.edit_text(f"❌ Error en modo autónomo: {e}")


# ─── Ralph Methodology ───────────────────────────────

async def ralphw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ralph Methodology: Meticulous, Autonomous, Iterative Development."""
    if not context.args:
        await update.message.reply_text("Uso: /ralphW <tarea de desarrollo>")
        return
    task = " ".join(context.args)
    status = await update.message.reply_text("🔬 Ralph Methodology activada. Ejecutando ciclo TDD...")

    thread_id = getattr(update.message, 'message_thread_id', None)
    session_id = f"topic_{thread_id}" if getattr(update.message, 'is_topic_message', False) and thread_id else memory_mod.current_session

    ralph_prompt = (
        f"[RALPH METHODOLOGY - AUTONOMOUS ITERATIVE DEVELOPMENT]\n\n"
        f"Task: {task}\n\n"
        "Follow the Ralph methodology strictly:\n"
        "1. ANALYZE: Understand requirements fully\n"
        "2. PLAN: Create a detailed step-by-step plan\n"
        "3. IMPLEMENT: Write code using [CALL_EXEC] to run scripts\n"
        "4. TEST: Verify each step works\n"
        "5. ITERATE: Fix issues and repeat until done\n\n"
        "Use your tools (CALL_EXEC, CALL_READ, CALL_MCP) to accomplish this autonomously."
    )

    try:
        result = await run_with_context(
            state.current_model, ralph_prompt, session_id=session_id,
            chat_id=update.effective_chat.id, thread_id=thread_id, max_depth=5
        )
        memory = load_memory(session_id)
        memory.append({"role": "user", "text": f"/ralphW {task}", "ts": datetime.now().isoformat()})
        memory.append({"role": "assistant", "text": result, "ts": datetime.now().isoformat()})
        save_memory(memory, session_id)
        await send_response(update, status, result)
        await broadcast_status("idle", "", agent="NoApiBot")
    except Exception as e:
        await status.edit_text(f"❌ Error en Ralph: {e}")


# ─── Usage Monitoring ─────────────────────────────────

async def probe_model(model: str):
    """Send a tiny probe to a model and return (status, seconds)."""
    import time
    start = time.time()
    try:
        result = await asyncio.wait_for(
            run_opencode(model, "Reply with exactly one word: OK"),
            timeout=30
        )
        elapsed = time.time() - start
        if "ok" in result.lower():
            return "✅", elapsed
        return "⚠️", elapsed
    except Exception:
        return "❌", time.time() - start


async def check_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check model usage and quotas."""
    status = await update.message.reply_text("📊 Verificando estado de modelos...")
    lines = ["📊 **Estado de Modelos Antigravity**\n"]
    for label, model_name in ANTIGRAVITY_MODELS.items():
        emoji, secs = await probe_model(model_name)
        lines.append(f"{emoji} {label}: `{model_name}` ({secs:.1f}s)")
    await status.edit_text("\n".join(lines), parse_mode="Markdown")


async def auto_refresh_models():
    """Ping all Antigravity models to keep the 5h refresh window alive."""
    print("🔄 Auto-refresh de modelos Antigravity...")
    for label, model_name in ANTIGRAVITY_MODELS.items():
        try:
            emoji, secs = await probe_model(model_name)
            print(f"   {emoji} {label}: {secs:.1f}s")
        except Exception as e:
            print(f"   ❌ {label}: {e}")
    print("🔄 Auto-refresh completado.")
