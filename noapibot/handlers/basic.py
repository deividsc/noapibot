"""
Basic handlers: /start, /models, /memory, /persona, /sessions, /remind, /exec, /bind.
"""
import re
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from noapibot.config import (
    DEFAULT_MODEL, DEFAULT_PERSONA, AGENTS_DIR, SKILLS_DIR,
    SESSIONS_DIR, OUTPUTS_DIR, EXEC_TIMEOUT,
)
from noapibot.memory import (
    load_memory, save_memory, load_qmd, load_persona, save_persona,
    load_reminders, save_reminders, load_topic_agents, save_topic_agents,
    load_json, save_json, _session_memory_file, generate_qmd_task,
    current_session,
)
from noapibot.core import run_opencode, send_response
from noapibot.websocket import broadcast_status
import noapibot.state as state
import noapibot.memory as memory_mod


# ─── /start ───────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **NoApiBot v4** en línea!\n\n"
        f"Modelo: `{state.current_model}` | Sesión: `{memory_mod.current_session}`\n\n"
        "📋 **General**\n"
        "/dashboard — Abrir Dashboard en navegador\n"
        "/models — Cambiar cerebro\n"
        "/statusbot — Estado del sistema\n"
        "/resetbot — Reiniciar bot\n\n"
        "🧠 **Memoria & Persona**\n"
        "/memory — Estado de memoria\n"
        "/forget — Borrar memoria\n"
        "/qmd — Comprimir memoria\n"
        "/persona — Ver personalidad\n"
        "/set\\_persona — Cambiar personalidad\n"
        "/agent — Activar agente\n\n"
        "📂 **Archivos & Sesiones**\n"
        "/read — Leer archivo\n"
        "/save — Guardar respuesta\n"
        "/pdf — Procesar PDF adjunto\n"
        "/docx — Procesar Word adjunto\n"
        "/pptx — Procesar PowerPoint adjunto\n"
        "/xlsx — Procesar Excel adjunto\n"
        "/new — Nueva sesión\n"
        "/sessions — Ver sesiones\n"
        "/switch — Cambiar sesión\n\n"
        "🔍 **Búsqueda & Investigación**\n"
        "/search — Buscar en internet\n"
        "/deep — Investigación profunda\n"
        "/trending — Tendencias X\n\n"
        "🌍 **Google Workspace**\n"
        "/gmail <query> — Consultar correos\n"
        "/drive <query> — Buscar en Drive\n"
        "/calendar <query> — Ver mi agenda\n"
        "/sheets <query> — Consultar Sheets\n"
        "/keep <query> — Ver mis notas\n\n"
        "🛠️ **Elite Skills**\n"
        "/sysmon — Monitor del sistema\n"
        "/vision <url> — Captura + OCR de web\n"
        "/git <cmd> — Operaciones Git\n"
        "/tree <path> — Árbol de directorio\n"
        "/runscript <path> — Ejecutar Python\n"
        "/api <method> <url> — Tester de APIs\n"
        "/docker <cmd> — Gestionar contenedores\n"
        "/lint <path> — Validar sintaxis\n"
        "/cv <datos> — Crear CV Optimizado\n"
        "/linkedin <tema> — Crear post\n"
        "/draft <edit> — Editar último borrador\n\n"
        "🔌 **MCP (Model Context Protocol)**\n"
        "/mcp <server> <tool> <args> — Ejecutar herramienta MCP\n"
        "/mcps — Ver servidores MCP configurados\n"
        "/auto <instrucción> — Agente Autónomo\n"
        "/ralphW <tarea> — Metodología Ralph (TDD autónomo)\n\n"
        "🗣️ **Voz**\n"
        "/habla — Leer texto en voz alta\n"
        "/hablame — Responder con nota de voz\n\n"
        "🐍 /exec — Ejecutar código/comando\n"
        "⏰ /remind — Programar recordatorio\n"
        "🧩 /skills — Ver skills disponibles\n\n"
        "O simplemente escríbeme.",
        parse_mode="Markdown"
    )


async def dashboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre el dashboard en el navegador local y envía instrucciones."""
    import webbrowser
    from noapibot.config import DASHBOARD_DIR
    
    index_path = DASHBOARD_DIR / "index.html"
    try:
        webbrowser.open(index_path.as_uri())
        await update.message.reply_text(
            "🌐 **Dashboard abierto!**\n\n"
            "Se ha intentado abrir el dashboard en tu navegador local.\n"
            f"Ruta: `{index_path}`\n\n"
            "Si no se abrió, puedes abrir ese archivo manualmente.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error al abrir el dashboard: {e}")


# ─── Models ───────────────────────────────────────────

async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎛️ Modelos:\n"
        "🟡 /gemini — Gemini 3.1 Pro\n"
        "🟡 /flash — Gemini 3 Flash\n"
        "🔵 /claude_opus — Claude Opus 4.6\n"
        "🔵 /claude_sonnet — Claude Sonnet 4.6\n"
        "🟣 /perplexity — Sonar Pro\n"
        "🟣 /perplexity_reason — Sonar Reasoning\n\n"
        f"Actual: `{state.current_model}`"
    )

async def _set_model(update, mid, engine="api"):
    state.current_model = mid
    state.current_engine = engine
    await update.message.reply_text(f"✔️ {state.current_model} (engine: {state.current_engine})")

async def set_gemini(u, c): await _set_model(u, "google/antigravity-gemini-3.1-pro", "api")
async def set_flash(u, c): await _set_model(u, "google/antigravity-gemini-3-flash", "api")
async def set_claude_opus(u, c): await _set_model(u, "google/antigravity-claude-opus-4-6", "opencode")
async def set_claude_sonnet(u, c): await _set_model(u, "google/antigravity-claude-sonnet-4-6", "opencode")
async def set_perplexity(u, c): await _set_model(u, "perplexity/sonar-pro", "opencode")
async def set_perplexity_reason(u, c): await _set_model(u, "perplexity/sonar-reasoning-pro", "opencode")


# ─── Memory & Persona ────────────────────────────────

async def show_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mem = load_memory()
    qmd_content = load_qmd()
    info = f"🧠 Memoria RAM: {len(mem)} msgs (Contexto local)\n"
    if qmd_content:
        info += f"🧠 Memoria ROM (QMD): Activa ({len(qmd_content)} chars)\n"
    else:
        info += "🧠 Memoria ROM (QMD): Vacía\n"
    await update.message.reply_text(info)

async def force_qmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory = load_memory()
    if len(memory) < 2:
        await update.message.reply_text("⚠️ No hay suficientes mensajes en la memoria RAM para compactar.")
        return
    status = await update.message.reply_text("🗜️ Comprimiendo el historial en el QMD (Fondo)...")
    try:
        to_summarize = memory.copy()
        memory = memory[-5:]
        save_json(_session_memory_file(memory_mod.current_session), memory)
        asyncio.create_task(generate_qmd_task(memory_mod.current_session, to_summarize))
        await status.edit_text("✅ Tarea de compresión QMD enviada a segundo plano.")
    except Exception as e:
        await status.edit_text(f"❌ Error al forzar QMD: {e}")

async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_memory([])
    await update.message.reply_text("🗑️ Memoria borrada.")

async def show_persona(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🎭 Personalidad:\n\n{load_persona()}")

async def set_persona_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = ' '.join(context.args) if context.args else None
    if not t:
        await update.message.reply_text("Uso: /set_persona <texto>")
        return
    save_persona(t)
    await update.message.reply_text("✔️ Personalidad actualizada.")

async def set_agent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.args[0] if context.args else None
    if not name:
        await update.message.reply_text("Uso: /agent <nombre_del_agente>")
        return
    agent_file = AGENTS_DIR / f"{name}.md"
    if not agent_file.exists():
        await update.message.reply_text(f"❌ Agente '{name}' no encontrado en {AGENTS_DIR}")
        return
    content = agent_file.read_text(encoding='utf-8')
    save_persona(content)
    state.active_skills.clear()
    match = re.search(r'^---\n.*?\bskills:\s*([^\n]+)\n.*?^---', content, re.MULTILINE | re.DOTALL)
    if match:
        skills_str = match.group(1)
        for s in [s.strip() for s in skills_str.split(',')]:
            if s:
                state.active_skills.append(s)
    await update.message.reply_text(
        f"🤖 Agente cambiado a: **{name}**\n🧩 Skills autocargados: {', '.join(state.active_skills) if state.active_skills else 'Ninguno'}"
    )

async def reset_persona_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state.active_skills.clear()
    save_persona(DEFAULT_PERSONA)
    await update.message.reply_text("🔄 He restaurado mi memoria base. Vuelvo a ser NoApiBot v4.0.")


# ─── Sessions ─────────────────────────────────────────

async def new_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.args[0] if context.args else None
    if not name:
        await update.message.reply_text("Uso: /new <nombre>\nEj: /new proyecto_web")
        return
    name = re.sub(r'[^\w-]', '_', name)
    memory_mod.current_session = name
    await update.message.reply_text(f"💬 Nueva sesión: `{memory_mod.current_session}` (memoria limpia)")

async def list_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = list(SESSIONS_DIR.glob("*.json"))
    if not files:
        await update.message.reply_text(f"💬 Solo sesión activa: `{memory_mod.current_session}`")
        return
    lines = []
    for f in sorted(files):
        data = load_json(f, [])
        active = "👉" if f.stem == memory_mod.current_session else "  "
        lines.append(f"{active} {f.stem} ({len(data)} msgs)")
    await update.message.reply_text("💬 Sesiones:\n" + "\n".join(lines) + f"\n\nActual: `{memory_mod.current_session}`")

async def switch_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.args[0] if context.args else None
    if not name:
        await update.message.reply_text("Uso: /switch <nombre>")
        return
    name = re.sub(r'[^\w-]', '_', name)
    session_file = SESSIONS_DIR / f"{name}.json"
    if not session_file.exists():
        await update.message.reply_text(f"❌ Sesión '{name}' no existe. Usa /new {name} para crearla.")
        return
    memory_mod.current_session = name
    mem = load_memory()
    await update.message.reply_text(f"💬 Cambiado a sesión: `{memory_mod.current_session}` ({len(mem)} msgs)")


# ─── Topic Binding ────────────────────────────────────

async def bind_topic_agent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post or update.edited_message
    if not getattr(msg, 'is_topic_message', False):
        await update.message.reply_text("❌ Este comando solo se puede usar dentro de un Tema/Topic.")
        return
    thread_id = str(msg.message_thread_id)
    agent_name = context.args[0] if context.args else None
    if not agent_name:
        await update.message.reply_text("Uso: /bind <nombre_del_agente>")
        return
    if agent_name.lower() == "noapibot":
        agent_name = "NoApiBot"
    else:
        agent_file = AGENTS_DIR / f"{agent_name}.md"
        if not agent_file.exists():
            await update.message.reply_text(f"❌ Agente '{agent_name}' no encontrado en {AGENTS_DIR}")
            return
    topic_agents = load_topic_agents()
    topic_agents[thread_id] = agent_name
    save_topic_agents(topic_agents)
    await update.message.reply_text(f"✅ Este Tema (Topic ID: {thread_id}) ahora está vinculado al agente: **{agent_name}**.", parse_mode="Markdown")


# ─── Reminders ────────────────────────────────────────

async def send_reminder(chat_id: int, text: str):
    try:
        await state.bot_app.bot.send_message(chat_id=chat_id, text=f"⏰ Recordatorio:\n\n{text}")
    except Exception as e:
        print(f"Error sending reminder: {e}")

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⏰ Uso:\n/remind 5m Tomar agua\n/remind 2h Revisar deploy\n/remind 14:30 Llamar al dentista"
        )
        return
    time_str = context.args[0]
    message = ' '.join(context.args[1:])
    chat_id = update.effective_chat.id
    now = datetime.now()
    match = re.match(r'^(\d+)(s|m|h)$', time_str)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {'s': timedelta(seconds=amount), 'm': timedelta(minutes=amount), 'h': timedelta(hours=amount)}[unit]
        run_at = now + delta
    elif re.match(r'^\d{1,2}:\d{2}$', time_str):
        h, m = map(int, time_str.split(':'))
        run_at = now.replace(hour=h, minute=m, second=0)
        if run_at <= now:
            run_at += timedelta(days=1)
    else:
        await update.message.reply_text("❌ Formato no reconocido. Usa: 5m, 2h, 14:30")
        return
    state.scheduler.add_job(send_reminder, 'date', run_date=run_at, args=[chat_id, message])
    reminders = load_reminders()
    reminders.append({"time": run_at.isoformat(), "message": message, "chat_id": chat_id})
    save_reminders(reminders)
    time_display = run_at.strftime("%H:%M:%S")
    await update.message.reply_text(f'✔️ Recordatorio programado para las {time_display}:\n"{message}"')

async def list_reminders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = load_reminders()
    if not reminders:
        await update.message.reply_text("📋 No hay recordatorios programados.")
        return
    lines = []
    for i, r in enumerate(reminders, 1):
        t = datetime.fromisoformat(r["time"]).strftime("%H:%M")
        lines.append(f"{i}. {t} — {r['message']}")
    await update.message.reply_text("⏰ Recordatorios:\n" + "\n".join(lines))


# ─── Code Execution ──────────────────────────────────

async def exec_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = ' '.join(context.args) if context.args else None
    if not cmd:
        await update.message.reply_text(
            "🐍 Uso:\n/exec python3 -c \"print(2+2)\"\n/exec ls /root/.openclaw/workspace/\n/exec cat /root/.openclaw/workspace/README.md"
        )
        return
    status = await update.message.reply_text("⚡ Ejecutando...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "openclaw-container", "bash", "-c", cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=EXEC_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await status.edit_text(f"⏱️ Timeout ({EXEC_TIMEOUT}s). Comando cancelado.")
            return
        result = out.decode('utf-8').strip()
        error = err.decode('utf-8').strip()
        output = ""
        if result:
            output += f"📤 Salida:\n```\n{result}\n```"
        if error:
            output += f"\n⚠️ Stderr:\n```\n{error}\n```"
        if not output:
            output = "✔️ Ejecutado sin salida."
        await send_response(update, status, output)
    except Exception as e:
        await status.edit_text(f"❌ {e}")


# ─── Status & Control ─────────────────────────────────

async def statusbot(update, context):
    import platform
    info = (
        f"🤖 **NoApiBot v4 Status**\n\n"
        f"Modelo: `{state.current_model}`\n"
        f"Engine: `{state.current_engine}`\n"
        f"Sesión: `{memory_mod.current_session}`\n"
        f"Skills activos: {len(state.active_skills)}\n"
        f"OS: {platform.system()} {platform.release()}\n"
        f"Python: {platform.python_version()}"
    )
    await update.message.reply_text(info, parse_mode="Markdown")

async def reboot_bot(update, context):
    await update.message.reply_text("🔄 Reiniciando...")
    import sys
    import os
    os.execv(sys.executable, [sys.executable] + sys.argv)
