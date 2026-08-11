---
name: pc-control
description: Hands on the local Mac for any agent - system state (battery, volume, brightness, IP), app launch/quit, open websites and YouTube, media and browser control via keystrokes, screenshots, clipboard, notifications, TTS, and honest mic/speaker hardware tests. Use whenever the user asks to control the computer, change volume or brightness, open an app or site, play or pause media, check battery/IP/running apps, take a screenshot, or test the mic or speakers. Rebuilt from the PC-Automation repo: the agent is the intent brain; this skill is only the hands.
---

# pc-control

One stdlib-only CLI gives the agent verified hands on this Mac. No third
party Python packages, no daemon, no interactive prompts. Every verb takes
arguments, returns useful text (or `--json`), and exits nonzero on failure
with a fix suggestion.

```bash
python3 ~/.claude/skills/pc-control/scripts/pc.py <command> [args] [--json]
```

## Start here

1. `pc.py doctor` - capability report. Run this first in a new environment;
   it tells you exactly which verbs are live and which are blocked by
   missing permissions, with the fix for each.
2. `pc.py <family> <action> --dry-run` - keystroke and URL verbs print what
   they would do without doing it. Use this when unsure.

## Verbs

### System state
| Command | Does |
|---|---|
| `battery` | percent, charging state, source, time remaining |
| `volume get\|set N\|up [N]\|down [N]\|mute\|unmute` | system output volume, 0-100 |
| `brightness up [steps]\|down [steps]` | display brightness via key codes (needs Accessibility) |
| `brightness get\|set V` | absolute values; works only where the DisplayServices API survives (broken on macOS 26, the command says so and points to up/down) |
| `ip [--public]` | local interface address; `--public` adds the WAN address |
| `apps [--all]` | visible apps, or every process with `--all` |
| `doctor` | environment and permission audit |

### Apps
| Command | Does |
|---|---|
| `app open NAME` | launch by name (`open -a`) |
| `app quit NAME` | graceful AppleScript quit; no-op if not running |
| `app activate NAME` | bring to front |
| `app front` | name of the frontmost app |
| `app running NAME` | true/false |

### Web and media sources
| Command | Does |
|---|---|
| `web NAME_OR_URL` | resolve and open: URL > cached name (assets/websites.json, 185 seeded) > https://name.com reachability guess (cached on success) > Google search page. Never scrapes search engines. |
| `youtube play QUERY` | fetches YouTube results, extracts the first videoId, opens the watch page directly; falls back to the results page offline |
| `youtube search QUERY` | opens the results page |

### Keystroke families (need the Accessibility grant, see Permissions)
| Command | Does |
|---|---|
| `browser ACTION` | 20 actions: new-tab, close-tab, reopen-tab, next-tab, prev-tab, new-window, private-window, zoom-in/out/reset, refresh, hard-refresh, back, forward, history, bookmarks, address-bar, find, devtools, fullscreen. Sent to the frontmost app; mappings are Chrome-family, most work in every Mac browser. |
| `yt ACTION` | 22 YouTube transport actions: play-pause, mute, fullscreen, theater, miniplayer, captions, vol-up/down, back-5/fwd-5, back-10/fwd-10, prev-frame/next-frame, speed-up/down, start, end, prev-chapter/next-chapter, next-video/prev-video. Focus a browser with YouTube first. |
| `media status\|play-pause\|play\|pause\|next\|prev` | app-aware: drives Spotify or Music directly via AppleScript when running (status includes track and artist); otherwise falls back to keystrokes at the frontmost app |
| `keys COMBO` | raw hand, e.g. `keys cmd+shift+t`, `keys f11`, `keys brightness-up` |
| `type TEXT` | types literal text into the frontmost app |

### Desktop utilities
| Command | Does |
|---|---|
| `screenshot [PATH]` | silent full-screen capture (needs Screen Recording permission) |
| `clipboard get\|set TEXT` | read or write the clipboard |
| `notify MSG [--title T] [--subtitle S]` | notification banner |
| `say TEXT [--voice V]` | speak through the speakers |

### Hardware tests
| Command | Does |
|---|---|
| `mic-test [--seconds N]` | records via ffmpeg, reports peak, clipping %, noise floor, SNR, and a verdict (detects silent/dead/denied mic) |
| `speaker-test [--measure] [--duration S]` | plays 4 tones plus a log sweep. Without `--measure` it says so honestly: playback is not proof of sound. With `--measure` it records through the mic during playback and reports which tones were actually heard. |

## Permissions (one-time, user must click these)

`doctor` detects all of these and prints the same fixes.

1. **Accessibility** (keystroke families): System Settings > Privacy &
   Security > Accessibility > enable the app hosting the agent (Claude,
   Terminal, iTerm...). Without it, every keystroke verb fails with error
   1002 and prints this fix.
2. **Microphone** (mic-test, speaker-test --measure): granted on first use
   prompt, or Privacy & Security > Microphone.
3. **Screen Recording** (screenshot): Privacy & Security > Screen Recording.

## Verification

`scripts/gate.py` is the measured gate: 49 checks including negative
tests and regression locks from the 6-agent adversarial verification of
2026-08-11, with volume and clipboard saved and restored. `gate.py --live` adds
a real keystroke round trip through TextEdit (type > select > copy >
compare clipboard) and requires the Accessibility grant. The gate prints a
NOT COVERED list; treat anything on that list as unverified.

## Design notes and limits

- Rebuilt 2026-08-11 from `AnubhavChaturvedi-GitHub/PC-Automation`. The
  original's 4,989-line phrase dictionary and fuzzy matcher were deleted:
  the calling agent is the intent recognizer now. Jokes/advice APIs and
  the file-creation parser were dropped; agents do those natively.
- macOS backend only. The code is layered so a Windows backend (the
  original's WMI/pycaw logic) can be added under the same verbs.
- Keystroke verbs act on the **frontmost app**, blind. Activate the right
  app first (`app activate NAME`) and prefer `--dry-run` when exploring.
- `browser history/bookmarks/devtools` shortcuts are Chrome-family;
  Safari differs for a few.
- Absolute brightness is an Apple API casualty on macOS 26; only stepping
  works, and only with Accessibility granted.
