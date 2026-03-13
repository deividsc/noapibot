"""Search handlers: /search, /deep, /trending."""
from telegram import Update
from telegram.ext import ContextTypes

from noapibot.core import run_opencode, send_response


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = ' '.join(context.args) if context.args else None
    if not q:
        await update.message.reply_text("Uso: /search <pregunta>")
        return
    s = await update.message.reply_text("🔍 Buscando...")
    try:
        await send_response(update, s, await run_opencode("perplexity/sonar-pro", q))
    except Exception as e:
        await s.edit_text(f"❌ {e}")


async def deep_research(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = ' '.join(context.args) if context.args else None
    if not q:
        await update.message.reply_text("Uso: /deep <pregunta>")
        return
    s = await update.message.reply_text("🔬 Investigación profunda...")
    try:
        await send_response(update, s, await run_opencode("perplexity/sonar-deep-research", q))
    except Exception as e:
        await s.edit_text(f"❌ {e}")


async def trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = ' '.join(context.args) if context.args else None
    prompt = (
        f"¿Qué se dice en X (Twitter) sobre '{topic}'? Tweets populares y sentimiento. Español."
        if topic else "Top 10 trending en X (Twitter) global ahora. Resumen breve. Español."
    )
    s = await update.message.reply_text("📡 Revisando X...")
    try:
        await send_response(update, s, await run_opencode("perplexity/sonar-pro", prompt))
    except Exception as e:
        await s.edit_text(f"❌ {e}")
