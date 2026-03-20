"""
Memory management for NoApiBot.
Handles sessions, QMD (Quick Memory Dump), persona, reminders, and topic agents.
"""
import json
import asyncio
from pathlib import Path

from noapibot.config import (
    SESSIONS_DIR, PERSONA_FILE, REMINDERS_FILE, TOPIC_AGENTS_FILE,
    DEFAULT_PERSONA, MAX_CONTEXT_MSGS,
)

# ─── State (mutable, shared across handlers) ─────────
current_session = "default"

# ─── JSON Helpers ─────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return default
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

# ─── Session Memory ──────────────────────────────────

def _session_memory_file(session_id=None):
    sid = session_id or current_session
    return SESSIONS_DIR / f"{sid}.json"

def _qmd_file(session_id=None):
    sid = session_id or current_session
    return SESSIONS_DIR / f"{sid}_QMD.md"

def load_memory(session_id=None):
    return load_json(_session_memory_file(session_id), [])

def load_qmd(session_id=None):
    qmd_path = _qmd_file(session_id)
    if qmd_path.exists():
        return qmd_path.read_text(encoding='utf-8')
    return ""

def save_memory(msgs, session_id=None):
    sid = session_id or current_session

    # Truncate individual messages to protect context window
    for m in msgs:
        text = m.get("text", "")
        if len(text) > 5000:
            m["text"] = text[:5000] + "\n\n[...Texto truncado por límite de memoria (5000 chars)...]"

    # If memory grows too large, truncate and launch background QMD compaction
    if len(msgs) > 15:
        to_summarize = msgs.copy()
        msgs = msgs[-5:]
        save_json(_session_memory_file(sid), msgs)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(generate_qmd_task(sid, to_summarize))
        except RuntimeError:
            pass
    else:
        save_json(_session_memory_file(sid), msgs)

# ─── QMD Generator ───────────────────────────────────

async def generate_qmd_task(session_id, memory_to_summarize):
    """Calls a lightweight model to compact raw history into the QMD document."""
    print(f"🧠 [QMD] Compactando memoria de sesión: {session_id}...")
    current_qmd = load_qmd(session_id)

    history_text = "\n".join(
        [f"[{m.get('role', 'Desconocido')}]: {m.get('text', '')}" for m in memory_to_summarize]
    )

    prompt = f"""
Eres un gestor de memoria a largo plazo (QMD - Quick Memory Dump).
Tu trabajo es mantener actualizado un documento Markdown con el perfil y contexto de esta sesión.

QMD ACTUAL:
'''
{current_qmd if current_qmd else 'Vacío. Esta es la primera compresión.'}
'''

HISTORIAL RECIENTE A COMPACTAR:
'''
{history_text}
'''

INSTRUCCIONES CRÍTICAS DE LÍMITE:
1. Extrae los datos importantes del historial (reglas establecidas, datos del usuario, tareas en progreso, contexto clave).
2. FUSIONA los datos nuevos con el QMD ACTUAL. 
3. Si una tarea ya fue completada, muévela a '## Historial / Log de Tareas Finalizadas'. 
4. NO repitas 'Decisiones Pendientes' que el usuario ya respondió. Solo mantén la decisión VITAL actual.
5. Formato: Markdown puro con secciones como: '## Perfil', '## Reglas', '## Contexto Actual', '## Historial de Tareas'.
6. MANTÉN EL QMD EXTREMADAMENTE CONCISO. NO SUPERES LAS 800 PALABRAS.
7. NO uses saludos ni explicaciones. Devuelve ÚNICAMENTE el código Markdown consolidado.
"""
    # Use Haiku for cheap/fast summarization (GCP — Anthropic via opencode)
    from noapibot.core import run_opencode
    new_qmd = await run_opencode("claude-haiku-4-5", prompt)

    # Clean markdown fences if the LLM wrapped the output
    if new_qmd.startswith('```'):
        lines = new_qmd.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines[-1].startswith('```'):
            lines = lines[:-1]
        new_qmd = '\n'.join(lines)

    _qmd_file(session_id).write_text(new_qmd.strip(), encoding='utf-8')
    print(f"🧠 [QMD] Archivo {_qmd_file(session_id).name} actualizado exitosamente.")

# ─── Reminders ────────────────────────────────────────

def load_reminders():
    return load_json(REMINDERS_FILE, [])

def save_reminders(r):
    save_json(REMINDERS_FILE, r)

# ─── Topic Agents ─────────────────────────────────────

def load_topic_agents():
    return load_json(TOPIC_AGENTS_FILE, {})

def save_topic_agents(t):
    save_json(TOPIC_AGENTS_FILE, t)

# ─── Persona ──────────────────────────────────────────

def load_persona():
    if PERSONA_FILE.exists():
        return PERSONA_FILE.read_text(encoding='utf-8').strip()
    PERSONA_FILE.write_text(DEFAULT_PERSONA, encoding='utf-8')
    return DEFAULT_PERSONA

def save_persona(t):
    PERSONA_FILE.write_text(t, encoding='utf-8')
