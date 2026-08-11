# PC-Automation v2: the pc-control agent skill

This repo is now an **agent skill**: it gives any AI agent (Claude Code or
anything that can run a CLI) verified hands on a Mac. One stdlib-only
Python CLI, no third party packages, no daemon, no interactive prompts.

```bash
python3 scripts/pc.py doctor
python3 scripts/pc.py volume set 40
python3 scripts/pc.py app open Safari
python3 scripts/pc.py youtube play "lo-fi beats"
python3 scripts/pc.py browser new-tab
python3 scripts/pc.py mic-test
```

Full verb catalog, permissions setup, and design notes: [SKILL.md](SKILL.md).

## Install as a Claude Code skill

```bash
git clone https://github.com/AnubhavChaturvedi-GitHub/PC-Automation.git ~/.claude/skills/pc-control
```

Then invoke `/pc-control` (or just ask the agent to control the computer).

## Why v2 looks nothing like v1

v1 (2024) was a console assistant: a 4,989-line phrase dictionary
fuzzy-matched typed English/Hindi commands to actions. LLM agents made
that entire layer obsolete: the agent is the intent recognizer now, so
only the actions survived. They were rebuilt as one non-interactive CLI
with `--json` and `--dry-run`, honest hardware tests (the speaker test
only claims success when it hears the tones through the mic), and a
measured verification gate (`scripts/gate.py`, 49 checks including
negative tests and regression locks).

v1 lives in this repo's git history (tag-free, see commits before the
2026-08-11 rebuild).

## Requirements

- macOS (backend is layered so a Windows backend can be added)
- Python 3.9+ (system python3 is fine, stdlib only)
- Optional: ffmpeg for mic capture, Accessibility permission for
  keystroke verbs (run `scripts/pc.py doctor`; it tells you exactly what
  is missing and how to fix it)
