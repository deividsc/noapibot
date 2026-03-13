"""
Core orchestration engine for NoApiBot.
Contains run_opencode (LLM execution) and run_with_context (tool interception + delegation).
"""
import re
import asyncio
import time
from datetime import datetime

import google.generativeai as genai

from noapibot.config import (
    ANTIGRAVITY_API_KEY, AGENTS_DIR, SKILLS_DIR, ANTIGRAVITY_SKILLS_DIR,
    GLOBAL_RULES_DIR, MAX_CONTEXT_MSGS, MCP_COOLDOWN_SECONDS,
)
from noapibot.memory import (
    load_memory, save_memory, load_qmd, load_persona, load_topic_agents,
)
from noapibot.websocket import broadcast_status, agent_metrics, bg_tasks
import noapibot.state as state

# ─── Regex ────────────────────────────────────────────
ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|(> build [^\n]+)|(\$ [^\n]+)')

# ─── Gemini SDK Init ─────────────────────────────────
if ANTIGRAVITY_API_KEY:
    genai.configure(api_key=ANTIGRAVITY_API_KEY)

# ─── LLM Runner ──────────────────────────────────────

async def run_opencode(model, prompt, attachment=None, engine_override=None, system_instruction=None):
    """Execute a prompt against an LLM (Gemini API, OpenCode CLI, Claude CLI, or Gemini CLI)."""
    engine = engine_override or state.current_engine

    # Auto-switch to opencode for non-Google models
    if engine == "api":
        lower_model = model.lower()
        is_google = "gemini" in lower_model or "flash" in lower_model or "pro" in lower_model
        if not is_google:
            print(f"🔄 Auto-routing '{model}' to 'opencode' engine (Not native Google).")
            engine = "opencode"

    if engine == "api":
        # Official Gemini API via SDK
        print(f"🟢 [API] Ejecutando {model} (Google SDK)...")
        api_model_name = "gemini-2.5-pro"
        if "pro" in model.lower():
            api_model_name = "gemini-2.5-pro"
        if "flash" in model.lower():
            api_model_name = "gemini-3-flash-preview"

        try:
            model_kw = {}
            if system_instruction:
                model_kw["system_instruction"] = system_instruction
            model_obj = genai.GenerativeModel(api_model_name, **model_kw)
            response = await model_obj.generate_content_async(prompt)
            text = response.text or "Sin respuesta de la API."
            return re.sub(r'\n\s*\n', '\n\n', text).strip()
        except Exception as e:
            return f"❌ Error en Gemini API: {str(e)}"

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
        # Resolve fully qualified model name for opencode CLI
        fq_model = model
        if "qwen" in model.lower() or "glm" in model.lower() or "kimi" in model.lower() or "minimax" in model.lower():
            if "/" not in model:
                fq_model = f"bailian-coding-plan/{model}"

        args = ["docker", "exec", "-i", "-w", "/root/.openclaw/workspace",
                "openclaw-container", "opencode", "run", "-m", fq_model]
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
            proc = await asyncio.create_subprocess_shell(
                " ".join(args), stdin=asyncio.subprocess.PIPE,
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
    memory = memory_override if memory_override is not None else load_memory(session_id)

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
    qmd_content = load_qmd(session_id)
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
    exec_match = re.search(r'\[CALL_EXEC:\s*(.*?)\s*\]', raw_response, re.DOTALL)
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

    # ─── CALL_EXEC ────────────────────────────────────
    elif exec_match:
        return await _handle_tool(
            agent_tools.execute_code, exec_match.group(1).strip(),
            "Ejecutando script de Python", "STD/ERR AL EJECUTAR EL SCRIPT",
            "El sistema ejecutó el código Python. Revisa el STDOUT/STDERR y formula la respuesta final",
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


# ─── Helper: Delegation Handler ──────────────────────

async def _handle_delegation(target_agent, message_to_send, current_agent_name, model, memory,
                             raw_response, depth, session_id, max_depth, chat_id, thread_id):
    """Handle CALL_MSG delegation to another agent via Telegram topics."""
    if not chat_id:
        return "Error: chat_id no está disponible en este contexto para enviar el mensaje."

    topic_agents = load_topic_agents()

    # Anti-loop check
    if target_agent.lower() == current_agent_name.lower():
        print(f"⚠️ Anti-Loop: Intentando delegar a sí mismo ({current_agent_name}).")
        memory.append({"role": "assistant", "text": raw_response, "ts": datetime.now().isoformat()})
        memory.append({"role": "tool", "text": f"ERROR: No puedes usar [CALL_MSG] para hablar contigo mismo ({current_agent_name}). Usa tus herramientas locales.", "ts": datetime.now().isoformat()})
        return await run_with_context(
            model, "Error de lógica: Intentaste delegar a ti mismo. Usa tus herramientas propias.",
            memory_override=memory, depth=depth + 1, session_id=session_id,
            max_depth=max_depth, chat_id=chat_id, thread_id=thread_id
        )

    # Map aliases
    aliases = {
        "project-planner": "noapibot", "planner": "noapibot", "planificador": "noapibot", "noapi": "noapibot",
        "investigador": "argos", "auditor": "argos", "coder": "cipher", "programador": "cipher"
    }
    canonical_target = aliases.get(target_agent.lower(), target_agent.lower())

    target_thread_id = None
    for tid, aname in topic_agents.items():
        if aname.lower() == canonical_target:
            target_thread_id = tid
            break

    if not target_thread_id:
        print(f"❌ Agente '{target_agent}' no encontrado en topic_agents.json")
        return f"Error: No se encontró ningún topic asignado al agente '{target_agent}'. Verifica el nombre."

    try:
        # Send visible message to Telegram
        try:
            await state.bot_app.bot.send_message(
                chat_id=chat_id, message_thread_id=int(target_thread_id),
                text=f"📥 **Mensaje de {current_agent_name}**\n\n{message_to_send}",
                parse_mode="Markdown"
            )
        except Exception:
            await state.bot_app.bot.send_message(
                chat_id=chat_id, message_thread_id=int(target_thread_id),
                text=f"📥 Mensaje de {current_agent_name} (Plain):\n\n{message_to_send}"
            )

        print(f"✅ Mensaje enviado a {target_agent} en topic {target_thread_id}")

        # Save to target agent memory and dispatch background processing
        target_session = f"topic_{target_thread_id}"
        target_mem = load_memory(target_session)
        target_mem.append({
            "role": "user",
            "text": f"[Mensaje interno de {current_agent_name}]: {message_to_send}",
            "ts": datetime.now().isoformat()
        })
        save_memory(target_mem, target_session)

        # Dispatch background task
        task = asyncio.create_task(
            _process_delegated_task(target_agent, target_thread_id, target_session,
                                   message_to_send, current_agent_name, thread_id, chat_id)
        )
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)

        return f"Mensaje enviado exitosamente al agente {target_agent}."

    except Exception as e:
        print(f"❌ Error al enviar mensaje: {e}")
        return f"Error al enviar mensaje a {target_agent}: {e}"


async def _process_delegated_task(t_agent, t_tid, t_session, msg, sender_name, origin_tid, chat_id):
    """Background task: target agent processes the delegated message."""
    await asyncio.sleep(2)
    try:
        print(f"🧠 Despertando a {t_agent} para procesar tarea de {sender_name}...")
        status_msg = await state.bot_app.bot.send_message(
            chat_id=chat_id, message_thread_id=int(t_tid),
            text=f"⏳ {t_agent} procesando mensaje de {sender_name}..."
        )

        target_reply = await run_with_context(
            state.current_model,
            f"[Mensaje interno de {sender_name}]: {msg}",
            session_id=t_session, chat_id=chat_id
        )

        target_mem = load_memory(t_session)
        target_mem.append({"role": "assistant", "text": target_reply, "ts": datetime.now().isoformat()})
        save_memory(target_mem, t_session)

        if len(target_reply) > 4000:
            await status_msg.delete()
            for i in range(0, len(target_reply), 4000):
                await state.bot_app.bot.send_message(chat_id=chat_id, message_thread_id=int(t_tid), text=target_reply[i:i+4000])
        else:
            await status_msg.edit_text(target_reply)

        await broadcast_status("idle", "", agent=t_agent)
        print(f"✅ {t_agent} terminó de procesar mensaje de {sender_name}.")

        # Callback to sender
        if sender_name:
            await _callback_to_sender(t_agent, sender_name, target_reply, origin_tid, chat_id)

    except Exception as e:
        print(f"❌ Error en tarea delegada a {t_agent}: {e}")
        await broadcast_status("idle", "", agent=t_agent)


async def _callback_to_sender(t_agent, sender_name, target_reply, origin_tid, chat_id):
    """Return the delegated result back to the sender agent."""
    callback_msg = (
        f"[Respuesta automática de {t_agent}]: Tarea finalizada.\n\n"
        f"Resultado/Reporte de {t_agent}:\n{target_reply}\n\n"
        "REGLA CRÍTICA: NO resumas el trabajo del agente (ya es visible arriba). "
        "Solo confirma que terminó y ofrece sugerencias de próximos pasos o preguntas de seguimiento. "
        "Responde de forma natural SIN negritas (**)."
    )
    print(f"🔄 Devolviendo resultado de {t_agent} a {sender_name}...")

    s_session = ""
    sender_tid = origin_tid

    if sender_name == "NoApiBot":
        s_session = "default"
    else:
        t_agents = load_topic_agents()
        for tid, aname in t_agents.items():
            if aname.lower() == sender_name.lower():
                sender_tid = tid
                break
        if sender_tid:
            s_session = f"topic_{sender_tid}"
        elif sender_name == "NoApiBot":
            s_session = "default"

    if not s_session:
        return

    try:
        await state.bot_app.bot.send_message(
            chat_id=chat_id,
            message_thread_id=int(sender_tid) if sender_tid else None,
            text=f"📥 **Retorno Automático de {t_agent}**\n\n_El agente ha completado la tarea. {sender_name} evaluando resultados..._",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    s_mem = load_memory(s_session)
    s_mem.append({"role": "user", "text": callback_msg, "ts": datetime.now().isoformat()})
    save_memory(s_mem, s_session)

    async def eval_callback():
        await asyncio.sleep(2)
        await broadcast_status("thinking", f"Evaluando retorno de {t_agent}...", agent=sender_name)
        eval_reply = await run_with_context(state.current_model, callback_msg, session_id=s_session, chat_id=chat_id)

        s_m = load_memory(s_session)
        s_m.append({"role": "assistant", "text": eval_reply, "ts": datetime.now().isoformat()})
        save_memory(s_m, s_session)

        if len(eval_reply) > 4000:
            for i in range(0, len(eval_reply), 4000):
                await state.bot_app.bot.send_message(chat_id=chat_id, message_thread_id=int(sender_tid) if sender_tid else None, text=eval_reply[i:i+4000])
        else:
            await state.bot_app.bot.send_message(chat_id=chat_id, message_thread_id=int(sender_tid) if sender_tid else None, text=eval_reply)

        await broadcast_status("idle", "", agent=sender_name)
        print(f"✅ Evaluación de {sender_name} completada.")

    cb_task = asyncio.create_task(eval_callback())
    bg_tasks.add(cb_task)
    cb_task.add_done_callback(bg_tasks.discard)


# ─── Utility ──────────────────────────────────────────

async def send_response(update, status_msg, text):
    """Send a response to Telegram, handling long messages by splitting."""
    if not text.strip():
        text = "Sin respuesta."
    if len(text) > 4000:
        await status_msg.delete()
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])
    else:
        await status_msg.edit_text(text)
