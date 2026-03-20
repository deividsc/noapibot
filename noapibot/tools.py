"""
Tool registry for NoApiBot agent system.
Each tool handles a specific CALL_* tag from the LLM response.
"""
import asyncio
import os
import json
import base64
import urllib.request
from typing import Dict, Any, Callable

from noapibot.config import SKILLS_DIR


async def analyze_image(image_path: str, prompt: str) -> str:
    """Process an image via Ollama Local (llava) to avoid API costs."""
    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode('utf-8')

        ollama_url = "http://localhost:11434/api/generate"
        payload = {
            "model": "llava:latest",
            "prompt": prompt,
            "images": [image_b64],
            "stream": False
        }

        def fetch_ollama():
            req = urllib.request.Request(
                ollama_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode('utf-8'))

        data = await asyncio.to_thread(fetch_ollama)
        res = data.get("response", "").strip()
        return res if res else "Ollama procesó la llamada pero devolvió un texto vacío."
    except Exception as e:
        return f"[ERROR DEL SISTEMA VISUAL OLLAMA] No se pudo analizar la imagen. Detalle: {str(e)}"


async def execute_search(query: str) -> str:
    """Search the internet using the local Docker container (Perplexity via opencode)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "openclaw-container",
            "opencode", "run", "-m", "perplexity/sonar-pro",
            f"Búsqueda ultra concisa y directa, solo quiero los hechos: {query}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        import re
        text = out.decode('utf-8').strip() or err.decode('utf-8').strip()
        text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|(> build [^\n]+)|(\$ [^\n]+)', '', text)
        return text if text else "No se encontraron resultados en la búsqueda."
    except Exception as e:
        return f"Error en la herramienta de búsqueda: {e}"



async def execute_read_file(path: str) -> str:
    """Read a local file and return its content.
    Only files inside ALLOWED_READ_DIRS (SEC-04/GCP) can be accessed.
    """
    import os
    from pathlib import Path

    # Allowlist of directories readable by agents (SEC-04/GCP)
    # DATA_DIR is the only safe dir in Cloud Run; extend via env var if needed.
    from noapibot.config import DATA_DIR
    raw_allowed = os.environ.get("NOAPIBOT_READ_DIRS", "")
    allowed_dirs = [Path(d).resolve() for d in raw_allowed.split(":") if d] or [DATA_DIR.resolve()]

    try:
        p = Path(path.strip()).resolve()  # resolve symlinks / .., no traversal

        # Enforce allowlist
        if not any(str(p).startswith(str(allowed)) for allowed in allowed_dirs):
            return (
                f"Acceso denegado: '{path}' está fuera de los directorios permitidos. "
                f"Dirs permitidos: {[str(d) for d in allowed_dirs]}"
            )

        if not p.exists():
            return f"Error: Archivo no encontrado en la ruta {path}"
        if not p.is_file():
            return f"Error: La ruta {path} es un directorio, no un archivo."

        content = p.read_text(encoding='utf-8', errors='replace')
        max_chars = 15000
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... [Truncado a {max_chars} chars]"
        return content
    except Exception as e:
        return f"Error al intentar leer el archivo: {e}"


async def execute_mcp(mcp_args: str) -> str:
    """Execute an MCP tool. Format: server_name tool_name {json_args}"""
    from pathlib import Path

    try:
        parts = mcp_args.strip().split(None, 2)
        if len(parts) < 2:
            return "Error: Formato debe ser: servidor herramienta {args_json}"

        server = parts[0]
        tool = parts[1]
        args_json = parts[2] if len(parts) > 2 else "{}"

        script = SKILLS_DIR / "mcp-client" / "scripts" / "mcp_execute.py"

        proc = await asyncio.create_subprocess_exec(
            "python", str(script), server, tool, args_json,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        except asyncio.TimeoutError:
            proc.kill()
            return "[TIMEOUT: La herramienta MCP tardó más de 60s y fue abortada.]"

        result = out.decode('utf-8', errors='replace').strip()
        if not result and err:
            result = err.decode('utf-8', errors='replace').strip()

        if len(result) > 3000:
            result = result[:3000] + "\n... [Truncado a 3000 chars]"

        return result if result else "[MCP ejecutado sin respuesta]"
    except Exception as e:
        return f"Error al ejecutar MCP: {e}"


async def execute_think(prompt: str) -> str:
    """Delegate complex reasoning to Claude Opus 4.6 (Specialist)."""
    try:
        import re
        specialist_model = "google/antigravity-claude-opus-4-6"

        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", "openclaw-container",
            "opencode", "run", "-m", specialist_model,
            "Respond to the STDIN prompt.",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            out, err = await asyncio.wait_for(proc.communicate(input=prompt.encode('utf-8')), timeout=120.0)
        except asyncio.TimeoutError:
            proc.kill()
            return "[TIMEOUT: El Especialista tardó más de 120s]"

        text = out.decode('utf-8', errors='replace').strip() or err.decode('utf-8', errors='replace').strip()
        text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
        text = re.sub(r'\n\s*\n', '\n\n', text).strip()

        if len(text) > 4000:
            text = text[:4000] + "\n... [Truncado a 4000 chars]"

        return text if text else "[Especialista no devolvió respuesta]"
    except Exception as e:
        return f"Error al consultar al Especialista: {e}"


async def execute_perplexica(query: str) -> str:
    """Search the internet using the local Docker Perplexica (SearxNG) container."""
    try:
        import sys
        # Try importing from skill scripts
        skill_script = SKILLS_DIR / "mcp-client" / "scripts" / "perplexica_tool.py"
        if str(skill_script.parent) not in sys.path:
            sys.path.append(str(skill_script.parent))

        import perplexica_tool
        result = await asyncio.to_thread(perplexica_tool.search_perplexica, query)
        return result
    except Exception as e:
        return f"Error al ejecutar Perplexica local: {e}"


def list_mcp_servers() -> str:
    """Read servers.json and return a summary of MCP servers for the system prompt."""
    servers_file = SKILLS_DIR / "mcp-client" / "servers.json"
    if not servers_file.exists():
        return ""
    try:
        servers = json.loads(servers_file.read_text(encoding="utf-8"))
        tool_hints = {
            "filesystem": "list_directory, read_file, write_file, search_files",
            "sqlite": "list_tables, read_query, write_query",
            "puppeteer": "puppeteer_navigate, puppeteer_screenshot, puppeteer_click",
            "notebooklm": "ask_notebook (args: notebook_name, query)",
            "everything": "echo, add, longRunningOperation",
            "perplexity": "pplx_ask, pplx_deep_research, pplx_claude_o46, pplx_gpt52, pplx_sonar (param: query)",
        }
        lines = []
        for name in servers:
            hints = tool_hints.get(name, "herramientas disponibles")
            lines.append(f"  - {name}: [{hints}]")
        return "\nServidores MCP disponibles para CALL_MCP:\n" + "\n".join(lines)
    except Exception:
        return ""


# ─── Tool Registry ────────────────────────────────────
TOOL_REGISTRY: Dict[str, Callable] = {
    '[CALL_SEARCH': execute_search,
    '[CALL_PPLX': execute_perplexica,
    # '[CALL_EXEC' removed — arbitrary code execution disabled (SEC-01/GCP)
    '[CALL_READ': execute_read_file,
    '[CALL_MCP': execute_mcp,
    '[CALL_THINK': execute_think,
    '[CALL_MSG': None  # Handled natively in core.py
}

TOOL_INSTRUCTIONS = (
    "\n\n[INSTRUCCIÓN VITAL DEL SISTEMA: ERES UN AGENTE AUTÓNOMO CON HERRAMIENTAS]\n"
    "A diferencia de un LLM normal, tú puedes usar herramientas ANTES de dar tu respuesta final al usuario.\n"
    "Si necesitas investigar internet, leer archivos, ejecutar código o usar servicios MCP, usa las herramientas:\n"
    "1. NO digas 'soy una IA y no sé' o 'no puedo ver tu disco'. NO pidas permiso al usuario.\n"
    "2. Para Búsqueda Web Rápida (SearxNG/Perplexica): `[CALL_PPLX: lo que quieres investigar profundamente]` (Recomendado para Sech/Investigación).\n"
    "3. Para Búsqueda Web Legacy (Opencode): `[CALL_SEARCH: lo que quieres buscar]`\n"
    "4. Para Leer un Archivo: `[CALL_READ: C:\\ruta\\absoluta\\al\\archivo.py]`\n"
    "5. [CALL_EXEC deshabilitado en entorno GCP por seguridad]\n"
    "6. Para Herramientas MCP: `[CALL_MCP: servidor herramienta {\"arg\":\"val\"}]`\n"
    "7. Para Razonamiento Complejo (Especialista): `[CALL_THINK: prompt detallado con contexto para el Arquitecto Senior]`\n"
    "8. Para Delegar a Otro Agente (Topic): `[CALL_MSG: nombre_agente | mensaje o tarea detallada]`\n"
    "   Úsalo para enviar mensajes o asignar tareas a otros agentes como 'sech', 'argos', etc.\n"
    "   IMPORTANTE: Al usar esta herramienta, tu ejecución actual SE DETENDRÁ. No intentes hacer la tarea tú mismo.\n"
    "   El otro agente recibirá el mensaje y responderá en su propio hilo/topic.\n"
    "SI USAS UNA HERRAMIENTA, el tag CALL_* debe ser TODO LO QUE ESCRIBAS. No saludes, no expliques. SOLO EL TAG."
)
