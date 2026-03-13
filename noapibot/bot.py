"""
NoApiBot - Telegram Bot Application.
Main entry point that wires all command handlers and starts the bot.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import asyncio
import json
from datetime import datetime

import websockets
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from noapibot.config import TELEGRAM_BOT_TOKEN, SKILLS_DIR, SESSIONS_DIR, DATA_DIR
from noapibot.memory import load_memory, save_memory, load_topic_agents
from noapibot.core import run_with_context, send_response
from noapibot.websocket import ws_handler, metrics_broadcaster, broadcast_status
import noapibot.state as state
import noapibot.memory as memory_mod

# ─── Handler Imports ──────────────────────────────────
from noapibot.handlers.basic import (
    start, list_models, set_gemini, set_flash, set_claude_opus, set_claude_sonnet,
    set_perplexity, set_perplexity_reason, show_memory, force_qmd, forget,
    show_persona, set_persona_cmd, set_agent_cmd, reset_persona_cmd,
    new_session, list_sessions, switch_session, bind_topic_agent_cmd,
    remind, list_reminders_cmd, exec_code, statusbot, reboot_bot, send_reminder,
    dashboard_cmd,
)
from noapibot.handlers.files import (
    read_file, save_file, pdf_cmd, pdfs_cmd, docx_cmd, docxs_cmd,
    pptx_cmd, pptxs_cmd, xlsx_cmd, xlsxs_cmd,
)
from noapibot.handlers.media import handle_voice, handle_photo, speak_text, speak_reply
from noapibot.handlers.search import search, deep_research, trending
from noapibot.handlers.skills import (
    list_skills, use_skill, sysmon_cmd, vision_cmd, git_cmd, search_cmd,
    tree_cmd, runscript_cmd, api_cmd, docker_cmd, lint_cmd, cv_cmd,
    linkedin_cmd, draft_cmd,
)
from noapibot.handlers.gws import gmail_cmd, drive_cmd, calendar_cmd, sheets_cmd, keep_cmd
from noapibot.handlers.advanced import (
    mcp_cmd, mcps_cmd, engine_cmd, claude_cmd, gemini_cmd,
    auto_cmd, ralphw_cmd, check_usage, auto_refresh_models,
)


# ─── Main Message Handler ────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process regular text messages."""
    msg = update.message
    if not msg or not msg.text:
        return

    user_msg = msg.text.strip()
    if not user_msg:
        return

    thread_id = getattr(msg, 'message_thread_id', None)
    is_topic = getattr(msg, 'is_topic_message', False)
    session_id = f"topic_{thread_id}" if is_topic and thread_id else memory_mod.current_session

    print(f"📩 [{session_id}] {user_msg[:80]}")

    try:
        status = await msg.reply_text(f"⏳ {state.current_model}...")
        memory = load_memory(session_id)
        memory.append({"role": "user", "text": user_msg, "ts": datetime.now().isoformat()})

        result = await run_with_context(
            state.current_model, user_msg, session_id=session_id,
            chat_id=update.effective_chat.id, thread_id=thread_id
        )

        memory.append({"role": "assistant", "text": result, "ts": datetime.now().isoformat()})
        save_memory(memory, session_id)

        await send_response(update, status, result)
        await broadcast_status("idle", "", agent="NoApiBot")

    except Exception as e:
        print(f"❌ Error: {e}")
        try:
            await msg.reply_text(f"❌ Error: {e}")
        except Exception:
            pass


# ─── Dynamic Workflow Handler ─────────────────────────

async def handle_dynamic_workflow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /slash commands that map to workflow files."""
    from noapibot.config import WORKFLOWS_DIR
    user_msg = update.message.text
    command_name = user_msg.split()[0][1:]

    workflow_file = WORKFLOWS_DIR / f"{command_name}.md"
    if not workflow_file.exists():
        await update.message.reply_text(f"❌ Workflow '{command_name}' no encontrado.")
        return

    workflow_content = workflow_file.read_text(encoding='utf-8')
    args_text = user_msg[len(command_name)+2:].strip() if len(user_msg) > len(command_name) + 1 else ""

    status = await update.message.reply_text(f"⚡ Ejecutando workflow: {command_name}...")
    prompt = f"[WORKFLOW: {command_name}]\n\nINSTRUCCIONES:\n{workflow_content}\n\nARGUMENTOS DEL USUARIO: {args_text}"

    try:
        result = await run_with_context(
            state.current_model, prompt, session_id=memory_mod.current_session,
            chat_id=update.effective_chat.id
        )
        await send_response(update, status, result)
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")


# ─── Main ─────────────────────────────────────────────

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    state.bot_app = app

    # ─── Register Commands ────────────────────────────
    # Core
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("dashboard", dashboard_cmd))
    app.add_handler(CommandHandler("models", list_models))
    app.add_handler(CommandHandler("statusbot", statusbot))
    app.add_handler(CommandHandler("resetbot", reboot_bot))

    # Models
    app.add_handler(CommandHandler("gemini", gemini_cmd))
    app.add_handler(CommandHandler("flash", set_flash))
    app.add_handler(CommandHandler("claude_opus", set_claude_opus))
    app.add_handler(CommandHandler("claude_sonnet", set_claude_sonnet))
    app.add_handler(CommandHandler("perplexity", set_perplexity))
    app.add_handler(CommandHandler("perplexity_reason", set_perplexity_reason))

    # Memory & Persona
    app.add_handler(CommandHandler("memory", show_memory))
    app.add_handler(CommandHandler("qmd", force_qmd))
    app.add_handler(CommandHandler("forget", forget))
    app.add_handler(CommandHandler("persona", show_persona))
    app.add_handler(CommandHandler("set_persona", set_persona_cmd))
    app.add_handler(CommandHandler("agent", set_agent_cmd))
    app.add_handler(CommandHandler("reset_persona", reset_persona_cmd))

    # Files
    app.add_handler(CommandHandler("read", read_file))
    app.add_handler(CommandHandler("save", save_file))
    app.add_handler(CommandHandler("pdf", pdf_cmd))
    app.add_handler(CommandHandler("pdfs", pdfs_cmd))
    app.add_handler(CommandHandler("docx", docx_cmd))
    app.add_handler(CommandHandler("docxs", docxs_cmd))
    app.add_handler(CommandHandler("pptx", pptx_cmd))
    app.add_handler(CommandHandler("pptxs", pptxs_cmd))
    app.add_handler(CommandHandler("xlsx", xlsx_cmd))
    app.add_handler(CommandHandler("xlsxs", xlsxs_cmd))

    # Sessions
    app.add_handler(CommandHandler("new", new_session))
    app.add_handler(CommandHandler("sessions", list_sessions))
    app.add_handler(CommandHandler("switch", switch_session))
    app.add_handler(CommandHandler("bind", bind_topic_agent_cmd))

    # Reminders
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("reminders", list_reminders_cmd))

    # Media
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("habla", speak_text))
    app.add_handler(CommandHandler("hablame", speak_reply))

    # Search
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("deep", deep_research))
    app.add_handler(CommandHandler("trending", trending))

    # Exec
    app.add_handler(CommandHandler("exec", exec_code))

    # Skills
    app.add_handler(CommandHandler("skills", list_skills))
    app.add_handler(CommandHandler("use", use_skill))
    app.add_handler(CommandHandler("sysmon", sysmon_cmd))
    app.add_handler(CommandHandler("vision", vision_cmd))
    app.add_handler(CommandHandler("git", git_cmd))
    app.add_handler(CommandHandler("tree", tree_cmd))
    app.add_handler(CommandHandler("runscript", runscript_cmd))
    app.add_handler(CommandHandler("api", api_cmd))
    app.add_handler(CommandHandler("docker", docker_cmd))
    app.add_handler(CommandHandler("lint", lint_cmd))
    app.add_handler(CommandHandler("cv", cv_cmd))
    app.add_handler(CommandHandler("linkedin", linkedin_cmd))
    app.add_handler(CommandHandler("draft", draft_cmd))

    # Google Workspace
    app.add_handler(CommandHandler("gmail", gmail_cmd))
    app.add_handler(CommandHandler("drive", drive_cmd))
    app.add_handler(CommandHandler("calendar", calendar_cmd))
    app.add_handler(CommandHandler("sheets", sheets_cmd))
    app.add_handler(CommandHandler("keep", keep_cmd))

    # MCP & Advanced
    app.add_handler(CommandHandler("mcp", mcp_cmd))
    app.add_handler(CommandHandler("mcps", mcps_cmd))
    app.add_handler(CommandHandler("auto", auto_cmd))
    app.add_handler(CommandHandler("ralphW", ralphw_cmd))
    app.add_handler(CommandHandler("engine", engine_cmd))
    app.add_handler(CommandHandler("claude", claude_cmd))
    app.add_handler(CommandHandler("usage", check_usage))

    # ─── Raw Update Logger ────────────────────────────
    async def raw_update_logger(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            msg = update.message or update.channel_post or update.edited_message
            text = msg.text if msg else "<no message>"
            chat_type = msg.chat.type if msg else "?"
            is_topic = getattr(msg, 'is_topic_message', None) if msg else None
            thread_id = getattr(msg, 'message_thread_id', None) if msg else None

            raw_data = update.to_dict()
            log_line = f"[UPDATE {update.update_id}] text='{text}' chat_type='{chat_type}' is_topic={is_topic} thread_id={thread_id} RAW={json.dumps(raw_data)}\n"
            print(log_line.strip(), flush=True)

            log_file = DATA_DIR / "bot_updates.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            print(f"[RAW LOGGER ERROR] {e}", flush=True)

    app.add_handler(MessageHandler(filters.ALL, raw_update_logger), group=-1)

    # Catch-all text handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ─── Post Init ────────────────────────────────────
    async def post_init(application):
        from noapibot.config import AUTO_OPEN_DASHBOARD, DASHBOARD_DIR
        import webbrowser
        
        try:
            await websockets.serve(ws_handler, "localhost", 8765)
            print("🌐 Dashboard WebSocket Server: ws://localhost:8765")
            asyncio.create_task(metrics_broadcaster())
            
            if AUTO_OPEN_DASHBOARD:
                index_path = DASHBOARD_DIR / "index.html"
                if index_path.exists():
                    print(f"🚀 Abriendo dashboard: {index_path}")
                    webbrowser.open(index_path.as_uri())
        except OSError as e:
            print(f"⚠️ WebSocket Server error (port busy?): {e}")

        state.scheduler.start()
        state.scheduler.add_job(auto_refresh_models, 'interval', hours=5, id='antigravity_refresh')
        print("⏰ Scheduler iniciado | 🔄 Auto-refresh: cada 5h")

    app.post_init = post_init
    
    # ─── Skill Discovery ──────────────────────────────
    def discover_skills():
        """Auto-populate state.active_skills with all found skills."""
        found = []
        # Single .md files
        for f in SKILLS_DIR.glob("*.md"):
            if f.stem not in found:
                found.append(f.stem)
        # Directory-based skills (with SKILL.md)
        for d in SKILLS_DIR.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                if d.name not in found:
                    found.append(d.name)
        state.active_skills = found
        print(f"✅ {len(found)} skills activados automáticamente: {', '.join(found)}")

    discover_skills()

    # ─── Error Handler ────────────────────────────────
    async def error_handler(update, context):
        print(f"🔴 [GLOBAL ERROR] {context.error}")
        import traceback
        traceback.print_exception(type(context.error), context.error, context.error.__traceback__)

    app.add_error_handler(error_handler)

    # ─── Start ────────────────────────────────────────
    print(f"🧩 Skills: {SKILLS_DIR}")
    print(f"💬 Sessions: {SESSIONS_DIR}")
    print(f"🔧 Engine: {state.current_engine} | Model: {state.current_model}")
    print("🚀 NoApiBot v4 iniciado! Esperando mensajes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
