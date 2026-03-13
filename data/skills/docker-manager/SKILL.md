---
name: docker-manager
description: Safely manage local Docker containers (list, logs, restart)
---

# 🐳 Docker Manager Skill

When working on backend projects like ExpenseManager, the user runs databases and APIs inside Docker containers. This skill lets you (NoApiBot) read the state of these containers and restart them if they crash.

## 🛠️ Usage

Use the `docker_ops.py` python wrapper to execute safe, pre-defined interactions with the Docker CLI. 

**To execute:**
Use your `[CALL_EXEC]` tool.

### 1. List Containers
Gets a formatted list of all active containers, their names, and their status (Up or Exited).
```python
import subprocess
print(subprocess.check_output('python ./data/skills/docker-manager/scripts/docker_ops.py ps', shell=True, text=True))
```

### 2. Read Container Logs
Fetches the last 50 lines of logs for a specific container to help you debug errors.
```python
import subprocess
print(subprocess.check_output('python ./data/skills/docker-manager/scripts/docker_ops.py logs "container_name"', shell=True, text=True))
```

### 3. Restart Container
Restarts a container if it's stuck or if you deployed new code.
```python
import subprocess
print(subprocess.check_output('python ./data/skills/docker-manager/scripts/docker_ops.py restart "container_name"', shell=True, text=True))
```

## 🚨 Rules
1. Never guess container names. Always run `ps` first to get the exact `NAMES` column.
2. The `logs` command only grabs the last 50 lines to prevent overwhelming your memory.
3. If Docker is not running or not installed, the script will tell you. Prompt the user to start Docker Desktop.
