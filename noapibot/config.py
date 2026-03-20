"""
Centralized configuration for NoApiBot.
All paths, env vars, and constants live here.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Environment ──────────────────────────────────────
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ─── Root Paths ───────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directory (persona, skills, sessions, memory)
# Auto-detect: prefer existing noapi_data/ for backward compatibility, else data/
_legacy_data = PROJECT_ROOT / "noapi_data"
_default_data = _legacy_data if _legacy_data.exists() else PROJECT_ROOT / "data"
DATA_DIR = Path(os.environ.get("NOAPIBOT_DATA_DIR", _default_data))
DATA_DIR.mkdir(exist_ok=True)

# Bot outputs (saved files, TTS audio, etc.)
_legacy_outputs = PROJECT_ROOT / "workspace" / "bot_outputs"
_default_outputs = _legacy_outputs if _legacy_outputs.exists() else PROJECT_ROOT / "outputs"
OUTPUTS_DIR = Path(os.environ.get("NOAPIBOT_OUTPUTS_DIR", _default_outputs))
OUTPUTS_DIR.mkdir(exist_ok=True)

# Skills directory
SKILLS_DIR = DATA_DIR / "skills"
SKILLS_DIR.mkdir(exist_ok=True)

# Sessions directory
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# Key files
PERSONA_FILE = DATA_DIR / "persona.txt"
REMINDERS_FILE = DATA_DIR / "reminders.json"
TOPIC_AGENTS_FILE = DATA_DIR / "topic_agents.json"

# ─── Agent Integration ────────────────────────────────
# Priority: env var > legacy Antigravity .agent path > bundled data/agents
_legacy_agents = PROJECT_ROOT / "workspace" / "MangaPipeline" / ".agent"
_bundled_agents = DATA_DIR / "agents"
if os.environ.get("NOAPIBOT_AGENTS_DIR"):
    AGENTS_BASE_DIR = Path(os.environ["NOAPIBOT_AGENTS_DIR"])
elif _legacy_agents.exists():
    AGENTS_BASE_DIR = _legacy_agents
else:
    AGENTS_BASE_DIR = DATA_DIR

# Resolve sub-paths
AGENTS_DIR = AGENTS_BASE_DIR / "agents" if (AGENTS_BASE_DIR / "agents").exists() else _bundled_agents
GLOBAL_RULES_DIR = AGENTS_BASE_DIR / "rules"
ANTIGRAVITY_SKILLS_DIR = AGENTS_BASE_DIR / "skills"
WORKFLOWS_DIR = AGENTS_BASE_DIR / "workflows"

# ─── Dashboard ────────────────────────────────────────
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"

# ─── Model Defaults ──────────────────────────────────
DEFAULT_MODEL = os.environ.get("NOAPIBOT_DEFAULT_MODEL", "claude-sonnet-4-6")
DEFAULT_ENGINE = os.environ.get("NOAPIBOT_DEFAULT_ENGINE", "opencode")
MAX_CONTEXT_MSGS = int(os.environ.get("NOAPIBOT_MAX_CONTEXT", "20"))
EXEC_TIMEOUT = int(os.environ.get("NOAPIBOT_EXEC_TIMEOUT", "30"))
AUTO_OPEN_DASHBOARD = os.environ.get("NOAPIBOT_AUTO_OPEN_DASHBOARD", "true").lower() == "true"

# ─── Persona ──────────────────────────────────────────
DEFAULT_PERSONA = (
    "ACTITUD Y NOMBRE:\n"
    "Eres NoApiBot v4.0, el Orquestador Supremo, Project Director y cerebro del proyecto. "
    "Vives en un entorno local y te conectas directamente a Telegram.\n\n"
    "CAPACIDADES CLAVE:\n"
    "Tienes control total sobre el sistema del usuario (escribiendo scripts, leyendo archivos, ejecutando MCPs). "
    "Pero tu mayor poder es la DIRECCIÓN DEL EQUIPO.\n"
    "Debes ser rápido para detectar si una tarea es simple y puedes solucionarla tú mismo, "
    "o si es compleja y requiere delegación mediante [CALL_MSG: bot | orden].\n\n"
    "AGENTES ESPECIALIZADOS A TU MANDO:\n"
    "- 'argos': Búsqueda y recopilación (Data Instigator)\n"
    "- 'aegis': DevOps y Seguridad\n"
    "- 'cipher': Programador Backend\n"
    "- 'nova': UI/Frontend en React/Web\n"
    "- 'sech': Búsquedas rápidas y sintéticas\n"
    "- 'neruda': Redacción persuasiva y Copywriting\n\n"
    "REGLAS DE INTERACCIÓN:\n"
    "1. Responde siempre en español fluido. Eres directivo pero muy servicial.\n"
    "2. PROHIBICIÓN TOTAL DE NEGRITAS: Está terminantemente prohibido usar doble asterisco (**) "
    "para resaltar palabras en charlas o explicaciones normales. Escribe de forma limpia y natural.\n"
    "3. PROTOCOLO DE DELEGACIÓN: Tienes prohibido autoinvestigar. Si el usuario pide investigar, "
    "buscar o saber algo que no sepas de memoria, DEBES delegar inmediatamente usando el comando "
    "[CALL_MSG: sech | instrucción]. NUNCA digas que delegas sin incluir el comando entre corchetes, "
    "de lo contrario la delegación fallará."
)

# ─── Telegram ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ─── API Keys ─────────────────────────────────────────
ANTIGRAVITY_API_KEY = os.environ.get("ANTIGRAVITY_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")

# ─── Rate Limiting ────────────────────────────────────
MCP_COOLDOWN_SECONDS = float(os.environ.get("NOAPIBOT_MCP_COOLDOWN", "3.5"))

# ─── Engram KV ────────────────────────────────────────
ENGRAM_URL = os.environ.get("ENGRAM_URL", "")

# ─── Startup Secret Validation (SEC-05/GCP) ──────────
# Fail fast if required secrets are missing — prevents silent failures in Cloud Run.
_REQUIRED_SECRETS = {
    "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
    "ENGRAM_URL": ENGRAM_URL,
}

def validate_secrets() -> None:
    """Call at app startup. Raises RuntimeError if any required secret is missing."""
    missing = [k for k, v in _REQUIRED_SECRETS.items() if not v]
    if missing:
        raise RuntimeError(
            f"Secrets obligatorios no configurados: {missing}. "
            "Configúralos en Secret Manager o en .env para desarrollo local."
        )

# ─── Antigravity Models ──────────────────────────────
ANTIGRAVITY_MODELS = {
    "🟡 Flash": "google/antigravity-gemini-3-flash",
    "🟡 Pro": "google/antigravity-gemini-3.1-pro",
    "🔵 Opus": "google/antigravity-claude-opus-4-6",
    "🔵 Sonnet": "google/antigravity-claude-sonnet-4-6",
}
