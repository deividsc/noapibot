---
name: python-runner
description: Write and execute temporary Python code to process data or test logic dynamically.
---

# 🐍 Python Runner Skill

This skill allows you (NoApiBot) to run arbitrary Python code safely. This is useful when you need to process large blocks of JSON data, calculate math, rename files in bulk, or verify Python logic before proposing a change to the user.

## 🛠️ Usage

Write your Python code to a temporary file, then use `safe_run.py` to execute it and capture the output safely.
First, write the python file you want to execute using your code generation abilities to any temporary folder (like `./workspace/temp_script.py`).

**To execute:**
Use your `[CALL_EXEC]` tool.

```python
import subprocess
print(subprocess.check_output('python ./data/skills/python-runner/scripts/safe_run.py "./workspace/temp_script.py"', shell=True, text=True))
```

## 🚨 Rules
1. Ensure your temporary scripts do not contain infinite loops.
2. The `safe_run.py` wrapper imposes a strict 60-second execution limit. If your script exceeds this, it will be forcefully terminated.
3. Both standard output (STDOUT) and errors (STDERR) are captured and returned to you. Use this feedback to debug your logic.
4. **Never run malicious code.** This runs on the user's host machine. Do not use this to delete core system files or download malware.
