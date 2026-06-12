#!/usr/bin/env python3
"""Sync local Codex history provider metadata after API/provider changes."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tarfile
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


def parse_args() -> argparse.Namespace:
    default_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    parser = argparse.ArgumentParser(
        description="Migrate Codex local history to the current model_provider.",
    )
    parser.add_argument("--codex-home", type=Path, default=default_home)
    parser.add_argument("--provider", help="Target provider. Defaults to config.toml model_provider.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    parser.add_argument(
        "--restart-app-server",
        action="store_true",
        help="After applying, terminate local 'codex app-server' processes so VS Code reloads state.",
    )
    parser.add_argument(
        "--skip-sqlite",
        action="store_true",
        help="Only update rollout JSONL files; leave state_5.sqlite unchanged.",
    )
    return parser.parse_args()


def read_provider_from_config(config_path: Path) -> str:
    if not config_path.exists():
        raise SystemExit(f"Missing config.toml: {config_path}")
    if tomllib is not None:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
        provider = data.get("model_provider")
        if isinstance(provider, str) and provider:
            return provider
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("model_provider"):
            _, value = stripped.split("=", 1)
            return value.strip().strip('"').strip("'")
    raise SystemExit(f"Could not find top-level model_provider in {config_path}")


def rollout_files(codex_home: Path) -> list[Path]:
    roots = [codex_home / "sessions", codex_home / "archived_sessions"]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(sorted(root.rglob("rollout-*.jsonl")))
    return files


def iter_session_meta(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "session_meta" and isinstance(obj.get("payload"), dict):
                yield obj


def jsonl_provider_counts(files: Iterable[Path]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in files:
        for obj in iter_session_meta(path):
            provider = obj["payload"].get("model_provider")
            if isinstance(provider, str):
                counts[provider] += 1
            else:
                counts["<missing>"] += 1
    return counts


def migrate_jsonl_file(path: Path, target_provider: str, apply: bool) -> int:
    original = path.read_text(encoding="utf-8")
    changed_records = 0
    output: list[str] = []
    for line in original.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        raw = line[:-1] if newline else line
        if not raw.strip():
            output.append(line)
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            output.append(line)
            continue
        payload = obj.get("payload")
        if (
            obj.get("type") == "session_meta"
            and isinstance(payload, dict)
            and payload.get("model_provider") != target_provider
        ):
            payload["model_provider"] = target_provider
            changed_records += 1
            output.append(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + newline)
        else:
            output.append(line)
    if apply and changed_records:
        path.write_text("".join(output), encoding="utf-8")
    return changed_records


def create_backup(codex_home: Path) -> Path:
    backups = codex_home / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backups / f"history-provider-sync-{stamp}.tar.gz"
    candidates = [
        codex_home / "sessions",
        codex_home / "archived_sessions",
        codex_home / "session_index.jsonl",
        codex_home / "state_5.sqlite",
        codex_home / "state_5.sqlite-wal",
        codex_home / "state_5.sqlite-shm",
    ]
    with tarfile.open(backup_path, "w:gz") as tar:
        for candidate in candidates:
            if candidate.exists():
                tar.add(candidate, arcname=candidate.relative_to(codex_home))
    return backup_path


def sqlite_provider_counts(db_path: Path) -> Counter[str]:
    if not db_path.exists():
        return Counter()
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("select model_provider, count(*) from threads group by model_provider").fetchall()
    finally:
        con.close()
    return Counter({str(provider): int(count) for provider, count in rows})


def migrate_sqlite(db_path: Path, target_provider: str, apply: bool) -> int:
    if not db_path.exists():
        return 0
    con = sqlite3.connect(db_path, timeout=30)
    try:
        count = con.execute(
            "select count(*) from threads where model_provider <> ?",
            (target_provider,),
        ).fetchone()[0]
        if apply and count:
            con.execute("update threads set model_provider = ? where model_provider <> ?", (target_provider, target_provider))
            con.commit()
        return int(count)
    finally:
        con.close()


def find_app_server_pids() -> list[int]:
    try:
        out = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
    except Exception:
        return []
    pids: list[int] = []
    for line in out.splitlines():
        if "codex app-server" not in line:
            continue
        parts = line.strip().split(maxsplit=1)
        if parts and parts[0].isdigit():
            pids.append(int(parts[0]))
    return pids


def restart_app_server() -> list[int]:
    pids = find_app_server_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    return pids


def print_counts(title: str, counts: Counter[str]) -> None:
    print(title)
    if not counts:
        print("  <none>")
        return
    for provider, count in sorted(counts.items()):
        print(f"  {provider}: {count}")


def main() -> int:
    args = parse_args()
    codex_home = args.codex_home.expanduser().resolve()
    if not codex_home.exists():
        raise SystemExit(f"CODEX_HOME does not exist: {codex_home}")

    target_provider = args.provider or read_provider_from_config(codex_home / "config.toml")
    files = rollout_files(codex_home)
    if not files:
        raise SystemExit(f"No rollout JSONL files found under {codex_home}/sessions or archived_sessions")

    print(f"CODEX_HOME: {codex_home}")
    print(f"Target provider: {target_provider}")
    print(f"Mode: {'apply' if args.apply else 'dry-run'}")
    print()

    before_jsonl = jsonl_provider_counts(files)
    print_counts("JSONL providers before:", before_jsonl)
    before_sqlite = sqlite_provider_counts(codex_home / "state_5.sqlite")
    print_counts("SQLite providers before:", before_sqlite)
    print()

    planned_files = 0
    planned_records = 0
    for path in files:
        changed = migrate_jsonl_file(path, target_provider, apply=False)
        if changed:
            planned_files += 1
            planned_records += changed

    sqlite_changes = 0 if args.skip_sqlite else migrate_sqlite(codex_home / "state_5.sqlite", target_provider, apply=False)
    print(f"JSONL records to update: {planned_records} in {planned_files} files")
    if not args.skip_sqlite:
        print(f"SQLite threads to update: {sqlite_changes}")

    backup_path: Path | None = None
    if args.apply and (planned_records or sqlite_changes):
        backup_path = create_backup(codex_home)
        print(f"Backup created: {backup_path}")
        for path in files:
            migrate_jsonl_file(path, target_provider, apply=True)
        if not args.skip_sqlite:
            migrate_sqlite(codex_home / "state_5.sqlite", target_provider, apply=True)
    elif not args.apply:
        print("Dry-run only. Re-run with --apply to write changes.")
    else:
        print("No changes needed.")

    print()
    after_jsonl = jsonl_provider_counts(files)
    print_counts("JSONL providers after:", after_jsonl)
    after_sqlite = sqlite_provider_counts(codex_home / "state_5.sqlite")
    print_counts("SQLite providers after:", after_sqlite)

    if args.restart_app_server:
        if not args.apply:
            print("Skipping app-server restart because --apply was not used.")
        else:
            pids = restart_app_server()
            print(f"Terminated codex app-server PIDs: {', '.join(map(str, pids)) if pids else '<none>'}")
    elif args.apply and (planned_records or sqlite_changes):
        print("Reload VS Code window if the Codex UI still shows the old history list.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
