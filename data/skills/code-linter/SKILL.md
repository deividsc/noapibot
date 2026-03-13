---
name: code-linter
description: Perform syntactic validation (linting) on Python scripts before executing or committing them.
---

# 🛡️ Code Linter Skill

This skill allows you (NoApiBot) to verify that a Python script has correct syntax (no missing colons, correct indentation, valid imports) before you attempt to run it or save it permanently. This acts as a safety net against hallucinated or malformed code.

## 🛠️ Usage

Use the `lint.py` python wrapper to structurally validate any `.py` file.

**To execute:**
Use your `[CALL_EXEC]` tool.

```python
import subprocess
print(subprocess.check_output('python ./data/skills/code-linter/scripts/lint.py "./workspace/your_script.py"', shell=True, text=True))
```

## 🚨 Rules
1. Always lint your Python code before presenting it to the user or pushing it to a repository.
2. If the linter returns an `IndentationError` or `SyntaxError`, you must fix the code and lint it again.
3. The linter uses `ast` parsing, so it only checks structural validity, not runtime logic errors.
