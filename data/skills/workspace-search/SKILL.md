---
name: workspace-search
description: Fast, recursive text search (like grep) to find functions, variables, or keywords across large codebases.
---

# 🔎 Workspace Search Skill

This skill gives you (NoApiBot) the ability to instantly find where a variable, function, or keyword is used across an entire project. It uses a custom Python script that recursively scans files, ignoring common binary and build directories.

## 🛠️ Usage

Use the python wrapper `fast_search.py` to search for text within a directory.
Always use your `[CALL_EXEC]` tool. 

**To execute:**
```python
import subprocess
# Replace 'your_search_term' and './search'
print(subprocess.check_output('python ./data/skills/workspace-search/scripts/fast_search.py "your_search_term" "./search"', shell=True, text=True))
```

## 🚨 Rules
1. **Be specific:** Searching for common words like "the" or "import" will return too many results. Search for specific variable names or function signatures.
2. The script provides the file path and the line number where the match occurred. Use this exact path with your `[CALL_READ]` tool if you need to inspect the surrounding code.
3. Path arguments must use absolute paths.
