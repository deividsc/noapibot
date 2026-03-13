---
name: task-status
description: Report progress back to the user on Telegram for long-running scripts (like MangaPipeline FFmpeg processing)
---

# 📊 Task Status Skill

This skill allows you (NoApiBot) to give the user live updates on long-running tasks. Since the bot engine is asynchronous, external scripts can push progress bar updates directly back to the active Telegram chat.

## 🛠️ Usage

When you launch a background process that will take more than a minute (like video rendering, data processing, or mass API calls), or if the user asks you for the status of a specific background job, you can use the `reporter.py` script.

**To execute:**
Use your `[CALL_EXEC]` tool.

### Sending a Live Progress Bar
Replace `CHAT_ID` with the user's Telegram ID (you must know it or ask). Find your token in the `.env` file or environment.

```python
import subprocess
print(subprocess.check_output('python ./data/skills/task-status/scripts/reporter.py progress 123456789 "Rendering Video Chapter 005..." 50 100', shell=True, text=True))
```
- Argument 1: Command (`progress` or `message`)
- Argument 2: User's Chat ID (e.g., `123456789`)
- Argument 3: The task description
- Argument 4: Current progress value (e.g., `50`)
- Argument 5: Maximum value (e.g., `100`)

### Developer Note
If you are writing scripts for the user (like updating MangaPipeline), you can inject `reporter.py` directly into those scripts so they auto-report their progress to Telegram.
