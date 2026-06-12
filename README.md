# Sync Codex History Provider

[English](README.md) | [简体中文](README.zh-CN.md)

Restore missing local Codex chat history after switching API keys, base URLs, or custom model providers.

This repository contains a Codex skill plus a standalone migration script. It is useful when the VS Code Codex extension or Codex UI suddenly shows only new conversations after changing `model_provider`, even though older history files still exist under `~/.codex`.

## What It Fixes

Codex stores local conversations as `rollout-*.jsonl` files under:

```text
~/.codex/sessions/
~/.codex/archived_sessions/
```

Each conversation has a `session_meta.payload.model_provider` value. After switching providers, for example from `api_key1` to `api_key2`, old conversations may still be tagged with the previous provider. Some Codex surfaces then show only conversations for the current provider, making older history look missing.

This tool updates the local metadata so old conversations belong to the current provider again.

## Safety

- Dry-run is the default.
- A timestamped backup is created before any write.
- Only `session_meta` records inside Codex JSONL files are edited.
- `auth.json` and API keys are never modified.
- SQLite state is updated after JSONL metadata, because JSONL is the source that can repopulate the state database.

## Install As A Codex Skill

### Natural Language Install

If you are not comfortable cloning into the Codex skills directory manually, open Codex and paste this:

```text
Please install this Codex skill from https://github.com/LinYangF/sync-codex-history-provider into my local Codex skills directory, then run its sync script in dry-run mode first. If the output looks correct, ask me before applying the migration.
```

Codex can clone the repository into the right location, inspect the dry-run output with you, and then apply the migration after you confirm.

### Manual Install

Clone the repository into your Codex skills directory:

```bash
git clone https://github.com/LinYangF/sync-codex-history-provider.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/sync-codex-history-provider"
```

Restart Codex or reload the VS Code window so the skill can be discovered.

After installation, ask Codex something like:

```text
Use sync-codex-history-provider to restore my missing Codex history after changing API provider.
```

## Run The Script Directly

Preview what would change:

```bash
python3 scripts/sync_codex_history_provider.py
```

Apply the migration:

```bash
python3 scripts/sync_codex_history_provider.py --apply
```

Use a specific Codex home:

```bash
python3 scripts/sync_codex_history_provider.py --codex-home ~/.codex --apply
```

Force a target provider instead of reading `config.toml`:

```bash
python3 scripts/sync_codex_history_provider.py --provider api_key2 --apply
```

Apply and terminate local `codex app-server` processes so the VS Code extension reloads state:

```bash
python3 scripts/sync_codex_history_provider.py --apply --restart-app-server
```

## Example Output

```text
CODEX_HOME: /home/sun/.codex
Target provider: api_key2
Mode: dry-run

JSONL providers before:
  api_key1: 71
  api_key2: 1
SQLite providers before:
  api_key1: 59
  api_key2: 1

JSONL records to update: 71 in 59 files
SQLite threads to update: 59
Dry-run only. Re-run with --apply to write changes.
```

## How It Works

The script:

1. Reads the current provider from `~/.codex/config.toml`.
2. Scans `sessions/` and `archived_sessions/` for `rollout-*.jsonl`.
3. Updates only records where `type == "session_meta"`.
4. Synchronizes `state_5.sqlite` so `threads.model_provider` matches.
5. Writes a backup to `~/.codex/backups/` before applying changes.

## Rollback

When run with `--apply`, the script prints the backup path. To inspect it:

```bash
tar -tzf ~/.codex/backups/history-provider-sync-YYYYMMDD-HHMMSS.tar.gz
```

To restore manually, extract the backup into `~/.codex` after closing Codex or VS Code.

## Requirements

- Python 3.11 or newer is recommended.
- Python 3.10 can work for most cases, but `tomllib` is built into Python 3.11+.
- The script uses only the Python standard library.

## Repository Contents

```text
SKILL.md
agents/openai.yaml
scripts/sync_codex_history_provider.py
```

## License

No license has been selected yet. Add one before inviting broad reuse or contributions.
