"""
Media handlers: voice messages, photo processing, TTS (/habla, /hablame).
"""
import re
import uuid
import tempfile
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from noapibot.config import OUTPUTS_DIR
from noapibot.memory import load_memory, save_memory
from noapibot.core import run_opencode, run_with_context, send_response
from noapibot.websocket import broadcast_status
import noapibot.state as state
import noapibot.memory as memory_mod


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download voice message, transcribe via LLM, then process as text."""
    msg = update.message
    voice = msg.voice or msg.audio
    if not voice:
        return

    status = await msg.reply_text("🎙️ Procesando audio...")

    try:
        file = await voice.get_file()
        tmp = tempfile.NamedTemporaryFile(suffix='.ogg', delete=False)
        await file.download_to_drive(tmp.name)

        # Transcribe using opencode with attachment
        transcription = await run_opencode(
            state.current_model,
            "Transcribe el siguiente audio al español. Solo devuelve la transcripción textual, sin explicaciones ni metadatos.",
            attachment=tmp.name
        )

        Path(tmp.name).unlink(missing_ok=True)

        await status.edit_text(f"📝 Transcripción: {transcription[:200]}...")

        # Process as regular message
        thread_id = getattr(msg, 'message_thread_id', None)
        is_topic = getattr(msg, 'is_topic_message', False)
        session_id = f"topic_{thread_id}" if is_topic and thread_id else memory_mod.current_session

        memory = load_memory(session_id)
        memory.append({"role": "user", "text": f"[Audio transcrito]: {transcription}", "ts": datetime.now().isoformat()})

        result = await run_with_context(state.current_model, transcription, session_id=session_id, chat_id=update.effective_chat.id, thread_id=thread_id)

        memory.append({"role": "assistant", "text": result, "ts": datetime.now().isoformat()})
        save_memory(memory, session_id)

        await send_response(update, status, result)
        await broadcast_status("idle", "", agent="NoApiBot")

    except Exception as e:
        await status.edit_text(f"❌ Error procesando audio: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download photo, submit to LLM with caption."""
    msg = update.message
    if not msg.photo:
        return

    caption = msg.caption or "Analiza esta imagen y describe lo que ves."
    status = await msg.reply_text("📸 Procesando imagen...")

    try:
        photo = msg.photo[-1]  # Highest resolution
        file = await photo.get_file()
        tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        await file.download_to_drive(tmp.name)

        thread_id = getattr(msg, 'message_thread_id', None)
        is_topic = getattr(msg, 'is_topic_message', False)
        session_id = f"topic_{thread_id}" if is_topic and thread_id else memory_mod.current_session

        result = await run_with_context(
            state.current_model, caption, attachment=tmp.name,
            session_id=session_id, chat_id=update.effective_chat.id, thread_id=thread_id
        )

        Path(tmp.name).unlink(missing_ok=True)

        memory = load_memory(session_id)
        memory.append({"role": "user", "text": f"[Imagen adjunta]: {caption}", "ts": datetime.now().isoformat()})
        memory.append({"role": "assistant", "text": result, "ts": datetime.now().isoformat()})
        save_memory(memory, session_id)

        await send_response(update, status, result)
        await broadcast_status("idle", "", agent="NoApiBot")

    except Exception as e:
        await status.edit_text(f"❌ Error procesando imagen: {e}")


async def speak_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a voice note from user text. /habla <text>"""
    from noapibot.tts import generate_speech

    text = ' '.join(context.args) if context.args else None
    if not text:
        await update.message.reply_text("🗣️ Uso: /habla <texto a leer en voz alta>")
        return

    out_file = OUTPUTS_DIR / f"tts_{uuid.uuid4().hex[:8]}.ogg"
    success = await generate_speech(text, str(out_file))
    if success:
        await update.message.reply_voice(voice=open(out_file, 'rb'))
    else:
        await update.message.reply_text("❌ Error generando voz.")


async def speak_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask LLM but reply with a voice note. /hablame <prompt>"""
    from noapibot.tts import generate_speech

    text = ' '.join(context.args) if context.args else None
    if not text:
        await update.message.reply_text("🗣️ Uso: /hablame <pregunta>")
        return

    status = await update.message.reply_text("🤔💬 Pensando y preparando voz...")
    try:
        result = await run_with_context(
            state.current_model, text, session_id=memory_mod.current_session,
            chat_id=update.effective_chat.id
        )

        # Save to memory
        memory = load_memory()
        memory.append({"role": "user", "text": text, "ts": datetime.now().isoformat()})
        memory.append({"role": "assistant", "text": result, "ts": datetime.now().isoformat()})
        save_memory(memory)

        # Generate voice from response
        out_file = OUTPUTS_DIR / f"tts_{uuid.uuid4().hex[:8]}.ogg"
        success = await generate_speech(result, str(out_file))
        if success:
            await status.delete()
            await update.message.reply_voice(voice=open(out_file, 'rb'), caption=result[:200])
        else:
            await send_response(update, status, result)
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")
