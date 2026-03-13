"""
Elite Skills handlers: /skills, /use, /sysmon, /vision, /git, /tree, /runscript, /api,
/docker, /lint, /cv, /linkedin, /draft, run_skill_script.
"""
import re
import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from noapibot.config import SKILLS_DIR, OUTPUTS_DIR
from noapibot.memory import load_memory
from noapibot.core import run_opencode, run_with_context, send_response
from noapibot.websocket import broadcast_status
import noapibot.state as state
import noapibot.memory as memory_mod


async def run_skill_script(update, context, script_path, args, status_text):
    """Unified wrapper to execute skill scripts safely and reply with output."""
    full_path = SKILLS_DIR / script_path
    if not full_path.exists():
        await update.message.reply_text(f"❌ Script `{script_path}` no encontrado.")
        return
    status = await update.message.reply_text(f"⚡ {status_text}...")
    try:
        cmd_args = ["python", str(full_path)] + [str(a) for a in args]
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(SKILLS_DIR)
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await status.edit_text("⏱️ Timeout (120s). Skill cancelado.")
            return
        result = out.decode('utf-8', errors='replace').strip()
        if not result and err:
            result = err.decode('utf-8', errors='replace').strip()
        await send_response(update, status, result if result else "✔️ Skill ejecutado sin salida.")
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")


async def list_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    legacy_skills = [f.stem for f in SKILLS_DIR.glob("*.md")]
    elite_skills = []
    slash_map = {
        "system-monitor": "/sysmon", "browser-vision": "/vision <url>",
        "git-essentials": "/git <cmd>", "workspace-search": "/search <dir> <term>",
        "task-status": "(interno)", "directory-tree": "/tree <dir>",
        "python-runner": "/runscript <path>", "api-tester": "/api <method> <url>",
        "docker-manager": "/docker <cmd>", "code-linter": "/lint <path>",
        "social-linkedin": "/linkedin <tema>  +  /draft <edit>",
        "mcp-client": "/mcp <api> <tool> <args>",
    }
    for d in sorted(SKILLS_DIR.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            elite_skills.append(d.name)
    if not legacy_skills and not elite_skills:
        await update.message.reply_text(f"🧩 No hay skills en `{SKILLS_DIR}`")
        return
    lines = []
    if elite_skills:
        lines.append("⚡ *Skills de Élite (Slash Commands):*")
        for s in elite_skills:
            cmd = slash_map.get(s, "")
            lines.append(f"  🔹 `{s}`  →  {cmd}")
    if legacy_skills:
        lines.append("\n🎭 *Skills de Persona (Prompts):*")
        for s in legacy_skills:
            active = "✅" if s in state.active_skills else "⬜"
            lines.append(f"  {active} `{s}`")
    lines.append("\n💡 Usa /use <nombre> para activar/desactivar personas.")
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')


async def use_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.args[0] if context.args else None
    if not name:
        await update.message.reply_text("Uso: /use <nombre_del_skill>")
        return
    
    file_path = SKILLS_DIR / f"{name}.md"
    dir_path = SKILLS_DIR / name / "SKILL.md"
    
    if not file_path.exists() and not dir_path.exists():
        await update.message.reply_text(f"❌ Skill '{name}' no existe en {SKILLS_DIR}")
        return
        
    if name in state.active_skills:
        state.active_skills.remove(name)
        await update.message.reply_text(f"⬜ Skill '{name}' desactivado.")
    else:
        state.active_skills.append(name)
        await update.message.reply_text(f"✅ Skill '{name}' activado.")


# ─── Elite Skill Commands ─────────────────────────────

async def sysmon_cmd(update, context):
    await run_skill_script(update, context, "system-monitor/scripts/sysmon.py", [], "Escaneando sistema")

async def vision_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /vision <url>")
        return
    await run_skill_script(update, context, "browser-vision/scripts/vision.py", context.args, f"Navegando a {context.args[0]}")

async def git_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /git <subcomando> [args]\nEj: /git status")
        return
    await run_skill_script(update, context, "git-essentials/scripts/git_tool.py", context.args, f"Git: {context.args[0]}")

async def search_cmd(update, context):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Uso: /search <directorio> <término>\nEj: /search D:\\proyecto async")
        return
    await run_skill_script(update, context, "workspace-search/scripts/search.py", context.args, f"Buscando '{context.args[-1]}'")

async def tree_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /tree <directorio>\nEj: /tree D:\\proyecto")
        return
    await run_skill_script(update, context, "directory-tree/scripts/tree.py", context.args, f"Generando árbol de {context.args[0]}")

async def runscript_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /runscript <path> [args]")
        return
    await run_skill_script(update, context, "python-runner/scripts/runner.py", context.args, f"Ejecutando {context.args[0]}")

async def api_cmd(update, context):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Uso: /api <method> <url>")
        return
    await run_skill_script(update, context, "api-tester/scripts/api_test.py", context.args, f"Testing {context.args[0]} {context.args[1]}")

async def docker_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /docker <subcomando> [args]")
        return
    await run_skill_script(update, context, "docker-manager/scripts/docker_tool.py", context.args, f"Docker: {context.args[0]}")

async def lint_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /lint <path>")
        return
    await run_skill_script(update, context, "code-linter/scripts/lint.py", context.args, f"Linting {context.args[0]}")

async def cv_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /cv <datos principales del candidato>")
        return
    status_msg = await update.message.reply_text("📝 Creando CV Optimizado...")
    try:
        datos = " ".join(context.args)
        prompt = f"Crea un CV profesional optimizado para ATS basado en estos datos: {datos}. Responde con HTML del CV."
        result = await run_with_context(state.current_model, prompt, session_id=memory_mod.current_session, chat_id=update.effective_chat.id)
        blocks = re.findall(r'```html\n(.*?)```', result, re.DOTALL)
        if blocks:
            html_content = blocks[0].strip()
            output_file = OUTPUTS_DIR / f"cv_output.html"
            output_file.write_text(html_content, encoding='utf-8')
            await update.message.reply_document(document=open(output_file, 'rb'), caption="📄 CV Generado")
            await status_msg.delete()
        else:
            await send_response(update, status_msg, result)
    except Exception as e:
        await status_msg.edit_text(f"❌ Error en CV Creator: {e}")

async def linkedin_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /linkedin <tema para el post>")
        return
    await run_skill_script(update, context, "social-linkedin/scripts/draft.py", context.args, "Redactando post (Jerome Style)")

async def draft_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Uso: /draft <instrucciones para modificar el post anterior>")
        return
    mem = load_memory()
    last_draft = None
    for msg in reversed(mem):
        if msg["role"] == "assistant" and "--- BORRADOR DE LINKEDIN ---" in msg["text"]:
            clean_text = msg["text"].replace("```text", "").replace("```", "").strip()
            last_draft = clean_text
            break
    if not last_draft:
        await update.message.reply_text("❌ No encontré ningún borrador de LinkedIn reciente en mi memoria para editar.")
        return
    script_args = list(context.args) + ["--context", last_draft]
    await run_skill_script(update, context, "social-linkedin/scripts/draft.py", script_args, "Pulir diamante (Editando Post)")
