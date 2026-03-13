---
name: git-essentials
description: Perform autonomous Git operations safely (status, add, commit, push) and keep track of changes.
---

# 🐙 Git Essentials Skill

This skill allows you (NoApiBot) to safely manage source control using Git. Instead of guessing complex terminal commands, you will use a dedicated python wrapper to perform actions.

## 🛠️ Usage

Use the python wrapper `git_ops.py` to interact with any repository.
Always use your `[CALL_EXEC]` tool. 

### 1. Check Status
Before making commits, ALWAYS check what files are modified.
```python
import subprocess
print(subprocess.check_output('python ./data/skills/git-essentials/scripts/git_ops.py status "./repo"', shell=True, text=True))
```

### 2. Auto-Commit (Add all & Commit)
This saves all current changes with a descriptive message.
```python
import subprocess
print(subprocess.check_output('python ./data/skills/git-essentials/scripts/git_ops.py commit "./repo" "Your detailed commit message here"', shell=True, text=True))
```

### 3. Push to Remote
Send local commits to GitHub/GitLab.
```python
import subprocess
print(subprocess.check_output('python ./data/skills/git-essentials/scripts/git_ops.py push "./repo"', shell=True, text=True))
```

## 🚨 Rules
1. **Always provide absolute paths** to the repository you want to manage.
2. If you are modifying code for the user, you should proactively `status` and `commit` your work so it acts as a save state.
3. Write clear, concise Git commit messages (e.g., "Fix: resolve JSON formatting issue in parser").
