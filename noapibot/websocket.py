"""
WebSocket server for the NoApiBot Dashboard.
Handles real-time status broadcasting and metrics tracking.
"""
import json
import asyncio
import websockets
from datetime import datetime

from noapibot.config import DEFAULT_MODEL

# ─── State ────────────────────────────────────────────
connected_clients = set()
agent_metrics = {}
bg_tasks = set()


async def ws_handler(websocket, path="/"):
    connected_clients.add(websocket)
    try:
        await websocket.send(json.dumps({"status": "idle", "task": ""}))
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "newTask":
                    task_text = data.get("title", "")
                    if task_text:
                        print(f"📥 [Dashboard] Nueva tarea recibida: {task_text}")
                        await _dispatch_dashboard_task(task_text)
            except Exception as e:
                print(f"❌ Error procesando mensaje del WS: {e}")
    finally:
        connected_clients.remove(websocket)


async def _dispatch_dashboard_task(task_text: str):
    """Process a task submitted from the Dashboard UI."""
    from noapibot.memory import load_memory, save_memory, current_session
    from noapibot.core import run_with_context
    from noapibot.state import current_model

    async def process():
        mem = load_memory(current_session)
        prompt = (
            f"[Dashboard Task] El usuario ha añadido una nueva tarea en el Dashboard. "
            f"Como Orquestador Principal, evalúa si puedes hacerla directamente o crea un plan "
            f"de acción para delegarla a los agentes especializados usando CALL_MSG. Misión: {task_text}"
        )
        mem.append({"role": "user", "text": prompt, "ts": datetime.now().isoformat()})
        await broadcast_status("thinking", f"Planificando: {task_text}", agent="NoApiBot")
        response = await run_with_context(current_model, prompt, session_id=current_session)
        mem.append({"role": "assistant", "text": response, "ts": datetime.now().isoformat()})
        save_memory(mem, current_session)
        await broadcast_status("idle", "", agent="NoApiBot")

    task = asyncio.create_task(process())
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)


async def broadcast_status(status: str, task: str = "", agent: str = "NoApiBot"):
    """Send an event status (thinking, researching, coding, idle) to the Dashboard UI."""
    from noapibot.state import current_model

    if agent not in agent_metrics:
        is_gemini = any(k in current_model for k in ("flash", "gemini", "pro"))
        agent_metrics[agent] = {
            "sessionLen": 0, "tokens": 0, "cost": 0.0, "reqs": 0,
            "limitType": "gemini" if is_gemini else "alibaba",
            "limitMax": 0.5 if is_gemini else 600,
            "status": "idle", "task": ""
        }

    agent_metrics[agent]["status"] = status
    agent_metrics[agent]["task"] = task

    if not connected_clients:
        return

    msg = json.dumps({
        "agent": agent, "status": status, "task": task,
        "monitor": agent_metrics[agent]
    })
    websockets.broadcast(connected_clients, msg)


async def metrics_broadcaster():
    """Background loop to track active session durations and update UI."""
    while True:
        await asyncio.sleep(1)
        updated = False
        for agent, metrics in agent_metrics.items():
            if metrics["status"] != "idle":
                metrics["sessionLen"] += 1
                updated = True

        if updated and connected_clients:
            for agent, metrics in agent_metrics.items():
                if metrics["status"] != "idle":
                    msg = json.dumps({
                        "agent": agent, "status": metrics["status"], "task": metrics["task"],
                        "monitor": metrics
                    })
                    websockets.broadcast(connected_clients, msg)
