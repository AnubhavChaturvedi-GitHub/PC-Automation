# PC-Automation: Give an AI Agent Real Hands on Your Mac

> A stdlib-only Python CLI that lets any AI agent control macOS: volume, brightness, apps, browser tabs, media playback, screenshots, clipboard, notifications and hardware tests. No third party packages, no daemon, no interactive prompts.

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![macOS](https://img.shields.io/badge/macOS-Supported-000000?style=for-the-badge&logo=apple&logoColor=white)](https://www.apple.com/macos/)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero-success?style=for-the-badge)](scripts/pc.py)
[![Stars](https://img.shields.io/github/stars/AnubhavChaturvedi-GitHub/PC-Automation?style=for-the-badge&color=yellow)](https://github.com/AnubhavChaturvedi-GitHub/PC-Automation/stargazers)

## What it does

Most desktop automation projects hardcode a list of phrases and guess at intent. This one does not. It exposes a clean, predictable verb catalog and lets the AI agent do the thinking. The agent decides *what* to do, this CLI is simply the hands that do it.

Every command is a single subprocess call, returns structured output, and never blocks waiting for input, which is exactly what an autonomous agent needs.

## Quick start

```bash
python3 scripts/pc.py doctor
python3 scripts/pc.py volume set 40
python3 scripts/pc.py app open Safari
python3 scripts/pc.py youtube play "lo-fi beats"
python3 scripts/pc.py browser new-tab
python3 scripts/pc.py mic-test
```

`doctor` is the one to run first. It reports which capabilities are available and which macOS permissions still need granting.

## Features

- **System state**: battery, volume, brightness, IP address, running apps
- **App control**: launch and quit any application by name
- **Web and media**: open URLs, search YouTube, play, pause, skip tracks
- **Browser control**: new tabs, navigation, window management
- **Capture**: screenshots and clipboard read/write
- **Output**: system notifications and text to speech
- **Hardware**: honest microphone and speaker tests that actually verify signal

The full verb catalog, permission setup and design notes live in [SKILL.md](SKILL.md).

## Install as a Claude Code skill

```bash
git clone https://github.com/AnubhavChaturvedi-GitHub/PC-Automation.git ~/.claude/skills/pc-control
```

Then invoke `/pc-control`, or just ask your agent to control the computer.

## Permissions

macOS gates several of these behind privacy settings. Grant your terminal (or the agent host app) access under:

- **System Settings > Privacy & Security > Accessibility** for keystrokes and window control
- **System Settings > Privacy & Security > Screen Recording** for screenshots
- **System Settings > Privacy & Security > Microphone** for mic tests

Run `doctor` after granting to confirm.

## Why v2 looks nothing like v1

v1 was a console assistant with a hardcoded phrase brain. v2 deletes that brain entirely. Modern AI agents already handle intent far better than a keyword table ever could, so the correct division of labour is: agent thinks, skill acts. The result is smaller, faster, dependency free and far more reliable.

## Requirements

macOS. Python 3.9 or newer (ships with the OS). Nothing to `pip install`.

## Contributing

Issues and pull requests welcome. New verbs should stay stdlib only and non-interactive.

## License

See the repository license file.

## Author

**Anubhav Chaturvedi**, founder of [NetHyTech](https://www.youtube.com/@NetHyTech), a developer community of 30,000+ members.

[![YouTube](https://img.shields.io/badge/YouTube-NetHyTech-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://www.youtube.com/@NetHyTech)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/anubhav-chaturvedi-/)

If this project saved you time, a star on the repo helps other people find it.
