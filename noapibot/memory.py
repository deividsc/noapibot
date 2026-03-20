"""
Memory management for noapibot GCP.

Session memory (conversation history) and QMD (Quick Memory Dump) are stored
in Engram KV when ENGRAM_URL is set, falling back to local JSON files for
local development.

Persona, agents, skills and rules remain as local files (config, not runtime state).
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path

from noapibot.config import (
    SESSIONS_DIR, PERSONA_FILE, REMINDERS_FILE, TOPIC_AGENTS_FILE,
    DEFAULT_PERSONA, MAX_CONTEXT_MSGS,
)
from noapibot.engram_client import engram_read, engram_write, ENGRAM_URL

# ─── State ────────────────────────────────────────────
current_session = "default"

# ─── Engram key helpers ───────────────────────────────

def _session_key(session_id: str) -> str:
    return f"session:{session_id}"

def _qmd_key(session_id: str) -> str:
    return f"qmd:{session_id}"

# ─── Local JSON fallback helpers ──────────────────────

def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"

def _qmd_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}_QMD.md"

def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── Session Memory ───────────────────────────────────

def load_memory(session_id=None) -> list:
    """Load session memory synchronously (from local JSON — used at request start)."""
    sid = session_id or current_session
    if ENGRAM_URL:
        # Synchronous wrapper: run async read in a new event loop if needed.
        # In practice, call load_memory_async from async contexts.
        try:
            loop = asyncio.get_running_loop()
            # We're inside an async context — return local file as fallback
            # (caller should use load_memory_async instead)
        except RuntimeError:
            pass
    return _load_json(_session_file(sid), [])


async def load_memory_async(session_id=None) -> list:
    """Load session memory from Engram KV (async, preferred in async contexts)."""
    sid = session_id or current_session
    if ENGRAM_URL:
        raw = await engram_read(_session_key(sid))
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
    return _load_json(_session_file(sid), [])


def save_memory(msgs: list, session_id=None):
    """Save memory synchronously to local file (called from sync contexts)."""
    sid = session_id or current_session
    _truncate_and_save(msgs, sid)


async def save_memory_async(msgs: list, session_id=None):
    """Save memory to Engram KV (preferred in async contexts)."""
    sid = session_id or current_session
    msgs = _prepare_msgs(msgs, sid)
    serialized = json.dumps(msgs, ensure_ascii=False)

    if ENGRAM_URL:
        await engram_write(_session_key(sid), serialized, tags=["session"])
    else:
        _save_json(_session_file(sid), msgs)


def _prepare_msgs(msgs: list, sid: str) -> list:
    """Truncate long messages and cap total count."""
    for m in msgs:
        text = m.get("text", "")
        if len(text) > 5000:
            m["text"] = text[:5000] + "\n\n[...Truncado por límite de memoria...]"

    if len(msgs) > 15:
        msgs = msgs[-5:]
        # QMD compaction is triggered separately via save_memory_async
    return msgs


def _truncate_and_save(msgs: list, sid: str):
    """Sync path: truncate + save local JSON + schedule QMD if needed."""
    to_summarize = None
    for m in msgs:
        text = m.get("text", "")
        if len(text) > 5000:
            m["text"] = text[:5000] + "\n\n[...Truncado...]"

    if len(msgs) > 15:
        to_summarize = msgs.copy()
        msgs = msgs[-5:]

    _save_json(_session_file(sid), msgs)

    if to_summarize:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(generate_qmd_task(sid, to_summarize))
        except RuntimeError:
            pass

# ─── QMD (Quick Memory Dump) ──────────────────────────

def load_qmd(session_id=None) -> str:
    sid = session_id or current_session
    qmd_path = _qmd_file(sid)
    if ENGRAM_URL:
        return ""  # async contexts should call load_qmd_async
    return qmd_path.read_text(encoding="utf-8") if qmd_path.exists() else ""


async def load_qmd_async(session_id=None) -> str:
    sid = session_id or current_session
    if ENGRAM_URL:
        return await engram_read(_qmd_key(sid))
    qmd_path = _qmd_file(sid)
    return qmd_path.read_text(encoding="utf-8") if qmd_path.exists() else ""


async def generate_qmd_task(session_id: str, memory_to_summarize: list):
    """Compact raw history into a QMD document using Haiku (cheap+fast)."""
    print(f"🧠 [QMD] Compactando sesión: {session_id}...")
    current_qmd = await load_qmd_async(session_id)

    history_text = "\n".join(
        [f"[{m.get('role', '?')}]: {m.get('text', '')}" for m in memory_to_summarize]
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
    from noapibot.core import run_opencode
    new_qmd = await run_opencode("claude-haiku-4-5", prompt)

    if new_qmd.startswith("```"):
        lines = new_qmd.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        lines = lines[:-1] if lines[-1].startswith("```") else lines
        new_qmd = "\n".join(lines)

    new_qmd = new_qmd.strip()
    if ENGRAM_URL:
        await engram_write(_qmd_key(session_id), new_qmd, tags=["qmd"])
    else:
        _qmd_file(session_id).write_text(new_qmd, encoding="utf-8")

    print(f"🧠 [QMD] Sesión {session_id} compactada.")

# ─── Reminders ────────────────────────────────────────

def load_reminders() -> list:
    return _load_json(REMINDERS_FILE, [])

def save_reminders(r: list):
    _save_json(REMINDERS_FILE, r)

# ─── Topic Agents (kept local — config, not state) ────

def load_topic_agents() -> dict:
    return _load_json(TOPIC_AGENTS_FILE, {})

def save_topic_agents(t: dict):
    _save_json(TOPIC_AGENTS_FILE, t)

# ─── Persona ──────────────────────────────────────────

def load_persona() -> str:
    if PERSONA_FILE.exists():
        return PERSONA_FILE.read_text(encoding="utf-8").strip()
    PERSONA_FILE.write_text(DEFAULT_PERSONA, encoding="utf-8")
    return DEFAULT_PERSONA

def save_persona(t: str):
    PERSONA_FILE.write_text(t, encoding="utf-8")
