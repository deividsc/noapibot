---
name: api-tester
description: Test REST API endpoints by sending GET, POST, PUT, DELETE requests and viewing JSON responses.
---

# 📡 API Tester Skill

This skill allows you (NoApiBot) to act like a headless Postman client. When you are debugging backend servers (like ExpenseManager API), you can send direct HTTP requests to verify endpoints, auth tokens, and payloads.

## 🛠️ Usage

Use the `api_call.py` python wrapper to send requests and cleanly print the response status and JSON body.

**To execute:**
Use your `[CALL_EXEC]` tool.

### Simple GET Request
```python
import subprocess
print(subprocess.check_output('python ./data/skills/api-tester/scripts/api_call.py GET "https://jsonplaceholder.typicode.com/todos/1"', shell=True, text=True))
```

### POST with JSON Payload and Headers
If you need to send complex payloads, write the payload to a `.json` file first (e.g. `./workspace/payload.json`) and headers to `./workspace/headers.json`, then pass their paths to the script.

```python
import subprocess
print(subprocess.check_output('python ./data/skills/api-tester/scripts/api_call.py POST "https://api.example.com/login" --payload "./workspace/payload.json" --headers "./workspace/headers.json"', shell=True, text=True))
```

## 🚨 Rules
1. Only pass exactly one method (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`) and one URL.
2. If the API returns standard HTML (like a 404 page), the tool will truncate the output to prevent spamming your context window.
3. Use this tool *proactively* when the user asks "Why is my login endpoint failing?". Spin up their local server via bash, hit the endpoint with this tool, and read the error!
