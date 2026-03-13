---
name: directory-tree
description: Generate a visual ASCII representation of a directory structure, ignoring heavy build folders.
---

# 🌳 Directory Tree Skill

This skill provides you with a way to instantly map out the architecture of a project before you start writing or modifying code. It generates a visual representation of folders and files.

## 🛠️ Usage

When you enter a new project or need to understand where components are located, always run the python wrapper `tree_gen.py`.

**To execute:**
Use your `[CALL_EXEC]` tool. 

```python
import subprocess
print(subprocess.check_output('python ./data/skills/directory-tree/scripts/tree_gen.py "./project"', shell=True, text=True))
```

## 🚨 Rules
1. **Always use this skill when opening a completely new repository.** It prevents you from wildly guessing file names.
2. The script ignores `.git`, `node_modules`, `venv`, and `__pycache__` to keep output clean and fast.
3. Use the absolute path returned by this tool in your `[CALL_READ]` tool when exploring files.
