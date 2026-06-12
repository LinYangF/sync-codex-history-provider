---
name: sync-codex-history-provider
description: Restore missing local Codex or VS Code Codex extension chat history after changing API keys, model providers, base URLs, or custom provider names. Use when old local conversations still exist under CODEX_HOME but the Codex UI only shows conversations for the current provider, or when Codex history needs provider metadata migrated across ~/.codex/sessions, archived_sessions, and state_5.sqlite.
---

# Sync Codex History Provider

## Overview

Use this skill to recover local Codex history that appears to disappear after switching API/provider configuration. The usual cause is provider filtering: old `rollout-*.jsonl` files still have `session_meta.payload.model_provider` set to an older provider, while the current `~/.codex/config.toml` points to a new provider.

## Workflow

1. Identify `CODEX_HOME`.
   - Prefer `$CODEX_HOME`.
   - Fall back to `~/.codex`.

2. Inspect, do not assume.
   - Confirm `config.toml` has the current `model_provider`.
   - Confirm history exists under `sessions/` or `archived_sessions/`.
   - Check provider distribution in both JSONL metadata and `state_5.sqlite`.

3. Run the bundled script in dry-run mode first:

```bash
python3 <skill-dir>/scripts/sync_codex_history_provider.py
```

4. If the dry-run output matches the intended migration, apply it:

```bash
python3 <skill-dir>/scripts/sync_codex_history_provider.py --apply
```

5. Restart the Codex VS Code extension app-server if the UI still shows the old list.
   - First try VS Code command: `Developer: Reload Window`.
   - If needed, run with `--restart-app-server` after confirming that killing the local `codex app-server` process is acceptable.

## Script

Use `scripts/sync_codex_history_provider.py`.

Important behavior:

- Defaults to dry-run.
- Reads the target provider from `config.toml` unless `--provider` is provided.
- Creates a timestamped backup under `CODEX_HOME/backups/` before applying.
- Only edits JSONL records where `type == "session_meta"`.
- Updates `state_5.sqlite.threads.model_provider` after JSONL migration.
- Does not print API keys or bearer tokens.

Common commands:

```bash
# Preview changes for the default CODEX_HOME.
python3 <skill-dir>/scripts/sync_codex_history_provider.py

# Apply changes using model_provider from config.toml.
python3 <skill-dir>/scripts/sync_codex_history_provider.py --apply

# Apply to a specific Codex home.
python3 <skill-dir>/scripts/sync_codex_history_provider.py --codex-home ~/.codex --apply

# Force a target provider instead of reading config.toml.
python3 <skill-dir>/scripts/sync_codex_history_provider.py --provider openai-custom --apply

# Apply and restart local codex app-server processes.
python3 <skill-dir>/scripts/sync_codex_history_provider.py --apply --restart-app-server
```

## Safety Notes

- Treat this as a local metadata migration, not a cloud sync.
- Do not delete session files to force a refresh.
- Do not edit `auth.json` or API keys.
- Keep the backup path from the script output so the user can roll back if needed.
- If Codex logs mention `state db discrepancy` after editing SQLite, migrate JSONL `session_meta` first; SQLite alone is not the source of truth.
