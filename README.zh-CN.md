# Sync Codex History Provider

[English](README.md) | [简体中文](README.zh-CN.md)

切换 API key、base URL 或自定义 model provider 后，恢复本地 Codex 聊天历史记录。

这个仓库包含一个 Codex skill 和一个可独立运行的迁移脚本。它适用于这种情况：你修改了 `model_provider` 后，VS Code Codex 扩展或 Codex UI 里只显示新对话，但旧历史文件其实仍然存在于 `~/.codex`。

## 解决什么问题

Codex 的本地对话通常保存为 `rollout-*.jsonl` 文件，位于：

```text
~/.codex/sessions/
~/.codex/archived_sessions/
```

每个对话文件里都有一个 `session_meta.payload.model_provider` 字段。切换 provider 后，例如从 `api_key1` 切到 `api_key2`，旧对话可能仍然标记为旧 provider。某些 Codex 界面会只展示当前 provider 下的对话，于是旧历史看起来就像“消失了”。

这个工具会更新本地元数据，让旧对话重新归属到当前 provider。

## 安全性

- 默认是 dry-run，不会直接修改文件。
- 真正写入前会自动创建带时间戳的备份。
- 只编辑 Codex JSONL 文件里 `type == "session_meta"` 的记录。
- 不会修改 `auth.json`，也不会修改 API key。
- 会先迁移 JSONL 元数据，再同步 SQLite 状态，因为 JSONL 可能会重新回填状态数据库。

## 安装为 Codex Skill

把仓库克隆到你的 Codex skills 目录：

```bash
git clone https://github.com/LinYangF/sync-codex-history-provider.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/sync-codex-history-provider"
```

然后重启 Codex，或者在 VS Code 中执行 `Developer: Reload Window`，让 Codex 重新发现这个 skill。

安装后，可以这样让 Codex 使用它：

```text
Use sync-codex-history-provider to restore my missing Codex history after changing API provider.
```

也可以直接用中文描述：

```text
使用 sync-codex-history-provider 帮我恢复切换 API provider 后消失的 Codex 历史记录。
```

## 直接运行脚本

先预览会改什么：

```bash
python3 scripts/sync_codex_history_provider.py
```

确认无误后应用迁移：

```bash
python3 scripts/sync_codex_history_provider.py --apply
```

指定 Codex home：

```bash
python3 scripts/sync_codex_history_provider.py --codex-home ~/.codex --apply
```

不从 `config.toml` 读取，而是手动指定目标 provider：

```bash
python3 scripts/sync_codex_history_provider.py --provider api_key2 --apply
```

应用迁移后终止本地 `codex app-server` 进程，让 VS Code 扩展重新加载状态：

```bash
python3 scripts/sync_codex_history_provider.py --apply --restart-app-server
```

## 示例输出

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

## 工作原理

脚本会：

1. 从 `~/.codex/config.toml` 读取当前 provider。
2. 扫描 `sessions/` 和 `archived_sessions/` 下的 `rollout-*.jsonl`。
3. 只更新 `type == "session_meta"` 的记录。
4. 同步 `state_5.sqlite`，让 `threads.model_provider` 保持一致。
5. 在真正写入前，把备份保存到 `~/.codex/backups/`。

## 回滚

使用 `--apply` 时，脚本会打印备份路径。可以先查看备份内容：

```bash
tar -tzf ~/.codex/backups/history-provider-sync-YYYYMMDD-HHMMSS.tar.gz
```

如果需要手动恢复，请先关闭 Codex 或 VS Code，再把备份解压回 `~/.codex`。

## 运行要求

- 推荐 Python 3.11 或更新版本。
- Python 3.10 大多数情况下也能运行，但 `tomllib` 是 Python 3.11+ 内置的。
- 脚本只依赖 Python 标准库。

## 仓库内容

```text
SKILL.md
agents/openai.yaml
scripts/sync_codex_history_provider.py
```

## License

暂时还没有选择 license。如果希望大家正式复用或贡献，建议后续添加一个开源许可证。
