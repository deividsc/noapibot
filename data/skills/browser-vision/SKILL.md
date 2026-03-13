---
name: browser-vision
description: Open a URL, bypass JS blockers (like Cloudflare), take a screenshot, and use local Ollama Vision to read the page.
---

# 👁️ Browser Vision Skill

This skill gives you (NoApiBot) the ability to "see" any website. Many modern sites block simple `curl` or `requests` using JavaScript challenges (like Cloudflare). This skill uses a real headless browser to render the page fully, takes a picture, and uses your local `llava:latest` model to read the visual data back to you.

## 🛠️ Usage

When the user asks you to "look at", "read", or "check" a specific website URL, you **MUST** run the `vision_capture.py` script.

**To execute:**
Use your `[CALL_EXEC]` tool with the following code:
```python
import subprocess
# Replace "https://example.com" with the requested URL. Keep the quotes.
print(subprocess.check_output('python ./data/skills/browser-vision/scripts/vision_capture.py "https://example.com"', shell=True, text=True))
```

## 🚨 Rules
1. Only pass exactly one URL as an argument inside quotes.
2. Be patient. Rendering a heavy site and spinning up `llava:latest` to process an image might take 10-30 seconds.
3. The script will return a detailed description of the site's layout and all readable text.
4. If the script complains that `playwright` is not installed, inform the user to run `pip install playwright` and `playwright install`.
