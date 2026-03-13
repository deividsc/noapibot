---
name: system-monitor
description: Monitor system resources (CPU, RAM, Disk, Network) in real-time.
---

# 💻 System Monitor Skill

This skill allows you (NoApiBot) to fetch detailed real-time statistics about the host machine's hardware resources. It uses a robust Python script based on `psutil` to prevent hallucinations and provide accurate data.

## 🛠️ Usage

When the user asks you about the computer's health, RAM usage, CPU load, or available disk space, you **MUST** run the `monitor.py` script.

**To execute:**
Use your `[CALL_EXEC]` tool with the following code:
```python
import subprocess
print(subprocess.check_output('python ./data/skills/system-monitor/scripts/monitor.py', shell=True, text=True))
```

## 📊 What data is returned?
- **CPU:** General load percentage and logical cores count.
- **RAM:** Total, Used, Free, and Active Percentage.
- **Disk:** Total capacity, Used space, Free space for the `D:\` drive (where OpenClaw runs).
- **Network:** Active bytes sent/received since boot.

## 🚨 Rules
1. **Never guess the metrics.** The user expects accurate, live numbers from their local machine.
2. Present the data clearly using Markdown (e.g., bullet points and bold text) and emojis for readability.
3. If the script fails, inform the user about the error cleanly.
