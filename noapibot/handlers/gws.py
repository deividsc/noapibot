"""Google Workspace handlers: /gmail, /drive, /calendar, /sheets, /keep."""
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from noapibot.memory import load_memory, save_memory
from noapibot.core import run_with_context, send_response
from noapibot.websocket import broadcast_status
import noapibot.state as state
import noapibot.memory as memory_mod


async def gws_generic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, service: str):
    """Abstraction layer for rapid Google Workspace commands."""
    if not context.args:
        await update.message.reply_text(
            f"🔍 Uso: `/{service} <consulta>`\nEj: `/{service} buscar presupuesto 2026`",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args)
    user_msg = f"[{service.upper()}] {query}"

    msg = update.message
    thread_id = getattr(msg, 'message_thread_id', None)
    is_topic = getattr(msg, 'is_topic_message', False)
    session_id = f"topic_{thread_id}" if is_topic and thread_id else memory_mod.current_session

    print(f"📩 [gws_cmd] {service}: '{query}' (Session: {session_id})")

    try:
        status = await msg.reply_text(f"⏳ NoApiBot consultando {service.capitalize()}...")
        memory = load_memory(session_id)
        memory.append({"role": "user", "text": f"/{service} {query}", "ts": datetime.now().isoformat()})

        result = await run_with_context(
            state.current_model, user_msg, session_id=session_id,
            chat_id=update.effective_chat.id, thread_id=thread_id
        )

        memory.append({"role": "assistant", "text": result, "ts": datetime.now().isoformat()})
        save_memory(memory, session_id)

        await send_response(update, status, result)
        await broadcast_status("idle", "", agent="NoApiBot")

    except Exception as e:
        print(f"❌ [gws_cmd] ERROR: {e}")
        await update.message.reply_text(f"❌ Error en /{service}: {e}")


async def gmail_cmd(u, c): await gws_generic_cmd(u, c, "gmail")
async def drive_cmd(u, c): await gws_generic_cmd(u, c, "drive")
async def calendar_cmd(u, c): await gws_generic_cmd(u, c, "calendar")
async def sheets_cmd(u, c): await gws_generic_cmd(u, c, "sheets")
async def keep_cmd(u, c): await gws_generic_cmd(u, c, "keep")
