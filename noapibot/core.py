"""
Core orchestration engine for NoApiBot.
Contains run_opencode (LLM execution) and run_with_context (tool interception + delegation).
"""
import re
import asyncio
import time
from datetime import datetime

from noapibot.config import (
    AGENTS_DIR, SKILLS_DIR, ANTIGRAVITY_SKILLS_DIR,
    GLOBAL_RULES_DIR, MAX_CONTEXT_MSGS, MCP_COOLDOWN_SECONDS,
)
from noapibot.memory import (
    load_memory_async, save_memory_async, load_qmd_async, load_persona,
)
from noapibot.websocket import broadcast_status, agent_metrics, bg_tasks
import noapibot.state as state

# ─── Regex ────────────────────────────────────────────
ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|(> build [^\n]+)|(\$ [^\n]+)')

# ─── LLM Runner ──────────────────────────────────────

async def run_opencode(model, prompt, attachment=None, engine_override=None, system_instruction=None):
    """Execute a prompt against an LLM (Gemini API, OpenCode CLI, Claude CLI, or Gemini CLI)."""
    engine = engine_override or state.current_engine

    final_prompt = prompt
    if system_instruction and engine != "api":
        # Structured format for Qwen/DeepSeek/etc to separate context from history
        final_prompt = (
            "### SYSTEM INSTRUCTIONS & CAPABILITIES ###\n"
            f"{system_instruction}\n\n"
            "### CONVERSATION HISTORY & CURRENT REQUEST ###\n"
            f"{prompt}"
        )

    if engine == "claude":
        args = ["claude", "--print", "--yes"]
    elif engine == "gemini":
        args = ["gemini", "ask", "--no-stream"]
    else:
        # opencode installed directly in container (GCP — no Docker-in-Docker)
        fq_model = model  # Anthropic models: "claude-sonnet-4-6", "claude-haiku-4-5"
        args = ["opencode", "run", "-m", fq_model]
        if attachment:
            args.extend(["-f", attachment])

    is_heavy = "perplexity" in model or "opus" in model or "sonnet" in model
    if is_heavy and engine == "opencode":
        print(f"🚦 [Semáforo] Esperando turno para {model}...")
        async with state.mcp_semaphore:
            now = time.time()
            elapsed = now - state.last_mcp_request_time
            if elapsed < MCP_COOLDOWN_SECONDS:
                wait = MCP_COOLDOWN_SECONDS - elapsed
                print(f"⏳ [Cooldown] Esperando {wait:.1f}s...")
                await asyncio.sleep(wait)
            state.last_mcp_request_time = time.time()
            print(f"🟢 [Semáforo] Ejecutando {model} (Engine: {engine})...")
            proc = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(input=final_prompt.encode('utf-8')), timeout=120)
            except asyncio.TimeoutError:
                proc.kill()
                return "❌ Timeout (120s): El modelo tardó demasiado en responder o el túnel está saturado."
    else:
        print(f"🟢 Ejecutando {model} (Engine: {engine})...")
        if engine != "opencode":
            # Use exec (not shell) to avoid shell injection (SEC-02/GCP)
            proc = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        try:
            out, err = await asyncio.wait_for(proc.communicate(input=final_prompt.encode('utf-8')), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            return "❌ Timeout (300s): El modelo tardó demasiado o la red está lenta. Reintenta."

    text = out.decode('utf-8').strip() or err.decode('utf-8').strip() or "Sin respuesta."
    text = ANSI_RE.sub('', text)
    return re.sub(r'\n\s*\n', '\n\n', text).strip()


# ─── Orchestration Engine ─────────────────────────────

async def run_with_context(model, user_msg, memory_override=None, depth=0, session_id=None,
                           attachment=None, max_depth=3, chat_id=None, thread_id=None):
    """
    Executes a prompt. If the model responds with a tool call [CALL_*: ...],
    it intercepts it, runs the tool, and recurses up to max_depth to formulate a final answer.
    """
    if depth > max_depth:
        return "❌ Límite de herramientas excedido (bucle infinito prevenido)."

    # Import tools lazily to avoid circular imports
    import noapibot.tools as agent_tools

    # Resolve agent persona from topic binding
    is_topic_session = session_id and str(session_id).startswith("topic_")
    topic_agent_content = None
    current_agent_name = "NoApiBot"
    if is_topic_session:
        thread_id = str(session_id).replace("topic_", "")
        topic_agents = load_topic_agents()
        bound_name = topic_agents.get(thread_id)
        if bound_name:
            current_agent_name = bound_name
            agent_file = AGENTS_DIR / f"{bound_name}.md"
            if agent_file.exists():
                topic_agent_content = agent_file.read_text(encoding='utf-8')

    raw_persona_text = topic_agent_content if topic_agent_content else load_persona()

    # Extract model override from agent frontmatter
    match_model = re.search(r'^---\n.*?\bmodel:\s*([^\n]+)\n.*?^---', raw_persona_text, re.MULTILINE | re.DOTALL)
    if match_model:
        m_val = match_model.group(1).strip()
        if m_val and m_val.lower() != "inherit":
            model = m_val

    persona = raw_persona_text + "\n\n" + agent_tools.TOOL_INSTRUCTIONS + agent_tools.list_mcp_servers()
    memory = memory_override if memory_override is not None else await load_memory_async(session_id)

    # Build system instruction
    protocol_parts = [
        "[PROTOCOLO DE ESTILO GLOBAL - APLICA A TODOS]\n"
        "1. PROHIBICIÓN TOTAL DE NEGRITAS: No uses el símbolo de doble asterisco (**) para resaltar texto. Escribe como un humano en un chat normal.\n"
        "2. TONO NATURAL: Evita listas robóticas, encabezados marcados (###) o tablas a menos que sea estrictamente necesario. Prefiere párrafos fluidos y naturales.\n"
        "3. PROHIBIDO: Generar marcadores vacíos como '** **' o '` `'.\n"
        "4. SALUDOS: Responde de forma cálida y humana (ej: 'Hola' si te saludan).\n"
        "5. RUTAS Y METADATA: Escribe rutas como texto plano. No incluyas bloques de log ```bash ``` a menos que ejecutes una herramienta real."
    ]

    if current_agent_name.lower() == "noapibot":
        protocol_parts.append(
            "[REGLA DE ORQUESTACIÓN - ESTRICTA]\n"
            "1. DELEGACIÓN OBLIGATORIA: Tienes prohibido autoinvestigar. Si el usuario pide investigar, buscar o saber algo que no sepas de memoria, DEBES delegar inmediatamente.\n"
            "2. SINTAXIS OBLIGATORIA: Para delegar, DEBES incluir el tag exacto `[CALL_MSG: sech | instrucciones detalladas]` en tu respuesta. Si omites el tag o los corchetes, la delegación no se ejecutará.\n"
            "3. NUNCA mientas diciendo 'Ya delegué' si no estás escribiendo el código [CALL_MSG] en esa misma respuesta."
        )

    sys_parts = [
        f"[Sistema] {persona}",
        "\n".join(protocol_parts),
        "[REPORTES TÉCNICOS (Solo bajo demanda)]\n"
        "- Usa tablas solo para planes de múltiples fases (sin usar negritas en las celdas).\n"
        "- Usa el bloque de Log final SOLAMENTE después de usar herramientas: ```bash\\n[OK] Acción realizada\\n```"
    ]

    # Inject QMD (silent context)
    qmd_content = await load_qmd_async(session_id)
    if qmd_content:
        sys_parts.append(f"[CONOCIMIENTO LATENTE DEL PROYECTO]: \n{qmd_content}\n")

    # Inject active skills
    for skill_name in state.active_skills:
        # 1. Check in ANTIGRAVITY_SKILLS_DIR (.agent/skills)
        # 2. Check in SKILLS_DIR (data/skills)
        # Support both: skill_name.md OR skill_name/SKILL.md
        
        found_content = None
        
        for base_dir in [ANTIGRAVITY_SKILLS_DIR, SKILLS_DIR]:
            file_path = base_dir / f"{skill_name}.md"
            dir_path = base_dir / skill_name / "SKILL.md"
            
            if file_path.exists():
                found_content = file_path.read_text(encoding='utf-8').strip()
                break
            elif dir_path.exists():
                found_content = dir_path.read_text(encoding='utf-8').strip()
                break
        
        if found_content:
            sys_parts.append(f"[Skill: {skill_name}]\n{found_content}")

    # Inject global rules
    if GLOBAL_RULES_DIR.exists():
        for rule_file in GLOBAL_RULES_DIR.glob("*.md"):
            sys_parts.append(f"[Global Rule: {rule_file.stem}]\n{rule_file.read_text(encoding='utf-8').strip()}")

    system_instruction_text = "\n".join(sys_parts)

    # Build conversation prompt
    parts = []
    for m in memory[-MAX_CONTEXT_MSGS:]:
        role = "Usuario" if m["role"] == "user" else ("Herramienta/Web" if m.get("role") == "tool" else "Asistente")
        parts.append(f"[{role}] {m['text']}")
    parts.append(f"[Usuario] {user_msg}")
    parts.append("[Asistente]")

    if depth == 0:
        await broadcast_status("thinking", "Analizando petición...", agent=current_agent_name)

    attachment_to_use = attachment if depth == 0 else None
    prompt_to_send = "\n".join(parts)

    # Metrics init
    if current_agent_name not in agent_metrics:
        is_gemini = "flash" in model or "gemini" in model or "pro" in model
        agent_metrics[current_agent_name] = {
            "sessionLen": 0, "tokens": 0, "cost": 0.0, "reqs": 0,
            "limitType": "gemini" if is_gemini else "alibaba",
            "limitMax": 0.5 if is_gemini else 600,
            "status": "idle", "task": ""
        }

    raw_response = await run_opencode(model, prompt_to_send, attachment=attachment_to_use, system_instruction=system_instruction_text)

    # Metrics tracking
    if current_agent_name in agent_metrics:
        char_count = len(prompt_to_send) + len(raw_response) + len(system_instruction_text)
        est_tokens = char_count // 4
        m = agent_metrics[current_agent_name]
        m["tokens"] += est_tokens
        m["reqs"] += 1
        m["cost"] += (est_tokens / 1_000_000) * 0.15

    # ─── Tool Interception ────────────────────────────
    search_match = re.search(r'\[CALL_SEARCH:\s*(.*?)\s*\]', raw_response, re.DOTALL)
    pplx_match = re.search(r'\[CALL_PPLX:\s*(.*?)\s*\]', raw_response, re.DOTALL)
    exec_match = None  # CALL_EXEC disabled — arbitrary code execution removed (SEC-01/GCP)
    read_match = re.search(r'\[CALL_READ:\s*(.*?)\s*\]', raw_response, re.DOTALL)
    mcp_match = re.search(r'\[CALL_MCP:\s*(.*?)\s*\]', raw_response, re.DOTALL)
    think_match = re.search(r'\[CALL_THINK:\s*(.*?)\s*\]', raw_response, re.DOTALL)
    msg_match = re.search(r'\[CALL_MSG:\s*(.*?)\s*\|\s*(.*?)\s*\]', raw_response, re.DOTALL)

    # ─── CALL_MSG (Delegation) ────────────────────────
    if msg_match:
        target_agent = msg_match.group(1).strip()
        message_to_send = msg_match.group(2).strip()
        print(f"✉️ Agent Tool Activada: Mensaje a '{target_agent}' -> '{message_to_send[:30]}...'")
        await broadcast_status("thinking", f"✉️ Enviando mensaje a {target_agent}...", agent=current_agent_name)

        tool_result = await _handle_delegation(
            target_agent, message_to_send, current_agent_name, model, memory,
            raw_response, depth, session_id, max_depth, chat_id, thread_id
        )

        memory.append({"role": "assistant", "text": raw_response, "ts": datetime.now().isoformat()})
        memory.append({"role": "tool", "text": f"RESULTADO ENVÍO MENSAJE:\n{tool_result}", "ts": datetime.now().isoformat()})
        await broadcast_status("idle", "", agent=current_agent_name)
        return f"✉️ {tool_result}"

    # ─── CALL_SEARCH ──────────────────────────────────
    elif search_match:
        return await _handle_tool(
            agent_tools.execute_search, search_match.group(1).strip(),
            "Buscando en web", "RESULTADO DE BÚSQUEDA WEB",
            "El sistema ejecutó la búsqueda web y obtuvo",
            current_agent_name, model, memory, raw_response, depth, session_id, max_depth, chat_id, thread_id
        )

    # ─── CALL_PPLX ────────────────────────────────────
    elif pplx_match:
        return await _handle_tool(
            agent_tools.execute_perplexica, pplx_match.group(1).strip(),
            "Investigando datos (Perplexica)", "RESULTADO DE PERPLEXICA DOCs/WEB",
            "Revisa los datos obtenidos por tu motor de investigación Perplexica y dame la síntesis final",
            current_agent_name, model, memory, raw_response, depth, session_id, max_depth, chat_id, thread_id
        )

    # ─── CALL_READ ────────────────────────────────────
    elif read_match:
        return await _handle_tool(
            agent_tools.execute_read_file, read_match.group(1).strip(),
            "Leyendo archivo local", "CONTENIDO DEL ARCHIVO",
            "Revisa el contenido del archivo obtenido y formula la respuesta final a mi solicitud inicial",
            current_agent_name, model, memory, raw_response, depth, session_id, max_depth, chat_id, thread_id
        )

    # ─── CALL_MCP ─────────────────────────────────────
    elif mcp_match:
        return await _handle_tool(
            agent_tools.execute_mcp, mcp_match.group(1).strip(),
            "🔌 MCP", "RESULTADO MCP",
            "El sistema ejecutó la herramienta MCP y obtuvo",
            current_agent_name, model, memory, raw_response, depth, session_id, max_depth, chat_id, thread_id
        )

    # ─── CALL_THINK ───────────────────────────────────
    elif think_match:
        return await _handle_tool(
            agent_tools.execute_think, think_match.group(1).strip(),
            "🧠 Consultando Arquitecto Senior (Opus)", "RESPUESTA DEL ESPECIALISTA (Claude Opus)",
            "El Especialista (Arquitecto Senior) respondió",
            current_agent_name, model, memory, raw_response, depth, session_id, max_depth, chat_id, thread_id
        )

    # No tool call — final response
    if depth == 0:
        await broadcast_status("idle", "", agent=current_agent_name)
    return raw_response


# ─── Helper: Generic Tool Handler ─────────────────────

async def _handle_tool(tool_fn, query, status_label, result_label, recurse_prompt,
                       agent_name, model, memory, raw_response, depth, session_id, max_depth, chat_id, thread_id):
    """Generic handler for all CALL_* tools except CALL_MSG."""
    print(f"🕵️ Agent Tool Activada: {status_label} '{query[:50]}...'")
    await broadcast_status("researching", f"{status_label}: {query[:50]}...", agent=agent_name)

    tool_result = await tool_fn(query)
    print(f"   Resultado ({len(tool_result)} chars obtenidos).")
    await broadcast_status("thinking", f"Analizando resultado...", agent=agent_name)

    memory.append({"role": "assistant", "text": raw_response, "ts": datetime.now().isoformat()})
    memory.append({"role": "tool", "text": f"{result_label} PARA '{query}':\n{tool_result}", "ts": datetime.now().isoformat()})

    return await run_with_context(
        model, f"{recurse_prompt}: {tool_result[:2000]}. Formula la respuesta final.",
        memory_override=memory, depth=depth + 1, session_id=session_id,
        max_depth=max_depth, chat_id=chat_id, thread_id=thread_id
    )


# ─── Helper: Delegation Handler (GCP — in-process, no Telegram) ──────────────

async def _handle_delegation(target_agent, message_to_send, current_agent_name, model, memory,
                             raw_response, depth, session_id, max_depth, chat_id, thread_id):
    """
    Delegate a task to another agent by calling run_with_context directly.
    No Telegram — the target agent runs in the same process and returns inline.
    """
    # Anti-loop check
    if target_agent.lower() == current_agent_name.lower():
        print(f"⚠️ Anti-Loop: {current_agent_name} intentó delegarse a sí mismo.")
        memory.append({"role": "assistant", "text": raw_response, "ts": datetime.now().isoformat()})
        memory.append({"role": "tool", "text": f"ERROR: No puedes delegar a ti mismo ({current_agent_name}).", "ts": datetime.now().isoformat()})
        return await run_with_context(
            model, "Error: Intentaste delegarte a ti mismo. Usa tus herramientas propias.",
            memory_override=memory, depth=depth + 1, session_id=session_id, max_depth=max_depth,
        )

    # Alias resolution
    aliases = {
        "project-planner": "noapibot", "planner": "noapibot", "planificador": "noapibot", "noapi": "noapibot",
        "investigador": "argos", "auditor": "argos", "coder": "cipher", "programador": "cipher"
    }
    canonical = aliases.get(target_agent.lower(), target_agent.lower())

    # Verify agent exists
    agent_file = AGENTS_DIR / f"{canonical}.md"
    if not agent_file.exists():
        return f"Error: Agente '{target_agent}' no encontrado en {AGENTS_DIR}. Agentes disponibles: {[f.stem for f in AGENTS_DIR.glob('*.md')]}"

    print(f"✉️ Delegando a '{canonical}' desde '{current_agent_name}'...")
    await broadcast_status("thinking", f"Delegando a {canonical}...", agent=current_agent_name)

    # Run target agent in-process with its own session
    target_session = f"agent_{canonical}"
    try:
        result = await run_with_context(
            model,
            f"[Mensaje interno de {current_agent_name}]: {message_to_send}",
            session_id=target_session,
            depth=0,
            max_depth=max_depth,
        )
    except Exception as e:
        result = f"Error al ejecutar agente '{canonical}': {e}"

    print(f"✅ '{canonical}' completó la delegación.")
    await broadcast_status("idle", "", agent=canonical)
    return result


