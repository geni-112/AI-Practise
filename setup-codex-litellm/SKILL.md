---
name: setup-codex-litellm
description: Configure an OpenAI-compatible Chat Completions model for Codex through a local LiteLLM Responses bridge. Use when a user wants to add a third-party model endpoint to Codex, create a separate selectable launcher without changing the default ChatGPT provider, or repair an existing LiteLLM-backed Codex model configuration on Windows.
---

# Setup Codex LiteLLM

Configure a third-party model without modifying the user's default Codex model or provider.

## Workflow

1. Run the bundled Windows configurator:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<skill-dir>\scripts\setup-codex-litellm.ps1"
   ```

2. Let the user fill the popup fields:
   - OpenAI-compatible base endpoint ending near `/v1`
   - API key
   - Exact model ID

3. Wait for the script to:
   - test `<endpoint>/chat/completions`;
   - install LiteLLM when missing;
   - store the key in a model-specific user environment variable;
   - create an isolated Codex home under `~/.codex-providers/`;
   - create a launcher named `codex-<model-slug>`;
   - preserve `~/.codex/config.toml` and the default ChatGPT provider.

4. Report the launcher command shown by the script. Tell the user to open a new PowerShell window if the command is not immediately found.

## Guardrails

- Never echo, log, or place the API key in TOML, YAML, command arguments, or chat.
- Do not add the third-party provider to the main `~/.codex/config.toml`.
- Treat this as a compatibility profile. Complex Codex tools may be unavailable because the upstream API is Chat Completions rather than Responses.
- If the endpoint already includes `/chat/completions`, allow the script to normalize it to the base URL.
- If validation fails, keep prior provider files intact and report the exact non-secret error.

## Noninteractive Automation

Only use noninteractive mode when the user explicitly supplies values through secure environment variables:

```powershell
$env:CODEX_COMPAT_ENDPOINT = "https://example.com/v1"
$env:CODEX_COMPAT_API_KEY = "<secret>"
$env:CODEX_COMPAT_MODEL = "model-id"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<skill-dir>\scripts\setup-codex-litellm.ps1" -NonInteractive
```
