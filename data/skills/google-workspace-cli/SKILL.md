---
name: google-workspace-cli
description: Official Google Workspace CLI (gws) for managing Gmail, Drive, Sheets, Calendar, Admin, Keep, and Meet.
allowed-tools: Run Command, Read, Write
---

# 🌐 Google Workspace CLI (gws)

This skill allows NoApiBot to interact directly with Google Workspace services using the official `gws` CLI tool. It provides a powerful way to automate tasks across Gmail, Drive, Sheets, and more.

## 🛠️ Usage Patterns

You can invoke `gws` commands directly via `[CALL_EXEC]`. The CLI follows a standard pattern:
`gws <service> <resource> [sub-resource] <method> [flags]`

### 📧 Gmail Examples
- **Check Inbox (Summary):** `gws gmail +triage` (Very efficient for NoApiBot)
- **Send email:** `gws gmail +send --to "user@example.com" --subject "Hello" --body "World"`
- **List messages:** `gws gmail users messages list --q "from:boss@example.com"`
- **Read message:** `gws gmail users messages get <id>`

### 📂 Google Drive Examples
- **Search files:** `gws drive files list --q "name contains 'Project'"`
- **Download file:** `gws drive files get <fileId> --alt media --out ./workspace/file.pdf`
- **Upload file:** `gws drive files create --name "data.csv" --file ./workspace/data.csv`

### 📊 Google Sheets Examples
- **Read sheet:** `gws sheets spreadsheets values get <spreadsheetId> --range "Sheet1!A1:B10"`
- **Append data:** `gws sheets spreadsheets values append <spreadsheetId> --range "Sheet1!A1" --values "[['New Data', 10]]"`

### 🗓️ Calendar Examples
- **List events:** `gws calendar events list primary`
- **Create event:** `gws calendar events insert primary --summary "Meeting" --start "2026-03-07T15:00:00Z" --end "2026-03-07T16:00:00Z"`

## 🚨 Setup & Authentication

1. **CLI Installation:** (Already done: `npm install -g @googleworkspace/cli`)
2. **Auth Login:** The user must run `gws auth login` once in the terminal to grant access if not already configured.
3. **Environment Variables:** You can also use `GOOGLE_WORKSPACE_CLI_TOKEN` or `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` for automated sessions.

## 💡 Best Practices
- Use `--format json` to get machine-readable output when you need to process data.
- Always check if the `gws` command is working by running `gws version` first.
- If a command fails due to "Unauthorized", prompt the user to run `gws auth login`.
