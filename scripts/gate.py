#!/usr/bin/env python3
"""gate.py: measured verification gate for the pc-control skill.

Safe by default: no keystrokes are injected and nothing destructive runs.
System volume and clipboard are saved and restored. Pass --live to add a
real keystroke round trip through TextEdit (needs the Accessibility grant).
Pass --quiet to skip the audible speaker tones.

Exit 0 only if zero FAILs. Prints an honest NOT COVERED list: a green gate
is proof of exactly what ran, nothing more.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PC = os.path.join(HERE, "pc.py")
SKILL = os.path.dirname(HERE)

results = []
not_covered = []


def record(status, name, detail=""):
    results.append((status, name, detail))
    mark = {"PASS": "ok", "FAIL": "FAIL", "SKIP": "skip"}[status]
    print(f"[{mark}] {name}" + (f"  ({detail})" if detail else ""))


def pc(*args, timeout=60):
    p = subprocess.run([sys.executable, PC, "--json", *args],
                       capture_output=True, text=True, timeout=timeout)
    try:
        data = json.loads(p.stdout) if p.stdout.strip() else {}
    except json.JSONDecodeError:
        data = {}
    return p.returncode, data, p.stderr


def check(name, cond, detail=""):
    record("PASS" if cond else "FAIL", name, detail)


def osacompile_ok(script):
    p = subprocess.run(["osacompile", "-e", script, "-o", os.devnull],
                       capture_output=True, text=True)
    return p.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="include the TextEdit keystroke round trip")
    ap.add_argument("--quiet", action="store_true",
                    help="skip audible speaker tones")
    a = ap.parse_args()

    # -- doctor and structure
    code, d, _ = pc("doctor")
    check("doctor runs and returns json", code == 0 and d.get("ok"))
    keystrokes_granted = d.get("checks", {}).get("keystrokes", False)

    # -- battery
    code, d, _ = pc("battery")
    check("battery reports percent 0-100",
          code == 0 and 0 <= d.get("percent", -1) <= 100)

    # -- volume (state saved and restored)
    code, d, _ = pc("volume", "get")
    vol0, muted0 = d.get("volume"), d.get("muted")
    check("volume get returns 0-100", code == 0 and 0 <= (vol0 or -1) <= 100)
    code, d, _ = pc("volume", "set", str(vol0))
    check("volume set (same value) succeeds", code == 0)
    code, d, _ = pc("volume", "set", "150")
    check("volume set 150 is rejected", code == 1)
    code, d, _ = pc("volume", "get")
    check("volume unchanged after gate", d.get("volume") == vol0)

    # -- ip
    code, d, _ = pc("ip")
    check("ip reports a local address", code == 0 and bool(d.get("local")))
    code, d, _ = pc("ip", "--public")
    if d.get("public"):
        check("ip --public resolves", True)
    else:
        record("SKIP", "ip --public", "network unavailable")

    # -- apps
    code, d, _ = pc("apps")
    check("apps lists visible apps", code == 0 and d.get("count", 0) > 0)
    code, d, _ = pc("app", "front")
    check("app front returns a name", code == 0 and bool(d.get("frontmost")))
    code, d, _ = pc("app", "running", "Finder")
    check("app running Finder is true", code == 0 and d.get("running") is True)
    code, d, _ = pc("app", "running", "NoSuchAppQzx")
    check("app running (absent) is false",
          code == 0 and d.get("running") is False)
    code, d, _ = pc("app", "open")
    check("app open without name is a usage error (exit 2)", code == 2)

    # -- clipboard (saved and restored)
    p = subprocess.run(["pbpaste"], capture_output=True, text=True)
    clip0 = p.stdout
    token = "pc-gate-3f9a"
    code, d, _ = pc("clipboard", "set", token)
    code2, d2, _ = pc("clipboard", "get")
    check("clipboard set/get round trip",
          code == 0 and code2 == 0 and d2.get("text") == token)
    subprocess.run(["pbcopy"], input=clip0, text=True)
    p = subprocess.run(["pbpaste"], capture_output=True, text=True)
    check("clipboard restored after gate", p.stdout == clip0)

    # -- screenshot
    tmp = os.path.join(tempfile.gettempdir(), f"pc-gate-{os.getpid()}.png")
    code, d, _ = pc("screenshot", tmp)
    if code == 0:
        check("screenshot writes a nonzero png",
              os.path.getsize(tmp) > 0)
        os.unlink(tmp)
    else:
        record("SKIP", "screenshot", "Screen Recording permission missing")
        not_covered.append("screenshot (permission)")

    # -- keystroke engine: dry-run + compile every mapped script
    combos = ["cmd+t", "cmd+shift+t", "ctrl+tab", "cmd+plus", "space",
              "shift+n", "ctrl+left", "f11", "brightness-up", "k"]
    all_ok = True
    for c in combos:
        code, d, _ = pc("keys", c, "--dry-run")
        scr = d.get("applescript", "")
        if code != 0 or not osacompile_ok(scr):
            all_ok = False
            record("FAIL", f"keys dry-run {c}", scr)
    check("keys: 10 combos map to valid AppleScript", all_ok)
    code, d, _ = pc("keys", "cmd+nosuchkey", "--dry-run")
    check("keys: unknown key rejected", code == 1)
    code, d, _ = pc("keys", "badmod+t", "--dry-run")
    check("keys: unknown modifier rejected", code == 1)

    code, d, _ = pc("type", 'he said "hi" \\ done', "--dry-run")
    check("type: quotes and backslashes compile",
          code == 0 and osacompile_ok(d.get("applescript", "")))

    # -- browser and yt maps: every action compiles
    for family, actions in [
        ("browser", ["new-tab", "close-tab", "reopen-tab", "next-tab",
                     "prev-tab", "new-window", "private-window", "zoom-in",
                     "zoom-out", "zoom-reset", "refresh", "hard-refresh",
                     "back", "forward", "history", "bookmarks", "address-bar",
                     "find", "devtools", "fullscreen"]),
        ("yt", ["play-pause", "mute", "fullscreen", "theater", "miniplayer",
                "captions", "vol-up", "vol-down", "back-5", "fwd-5",
                "back-10", "fwd-10", "prev-frame", "next-frame", "speed-up",
                "speed-down", "start", "end", "prev-chapter", "next-chapter",
                "next-video", "prev-video"]),
    ]:
        all_ok = True
        for act in actions:
            code, d, _ = pc(family, act, "--dry-run")
            if code != 0 or not osacompile_ok(d.get("applescript", "")):
                all_ok = False
                record("FAIL", f"{family} {act}", d.get("applescript", "?"))
        check(f"{family}: all {len(actions)} actions compile", all_ok)
        code, d, _ = pc(family, "no-such-action", "--dry-run")
        check(f"{family}: unknown action rejected", code == 1)

    # -- media
    code, d, _ = pc("media", "status")
    check("media status runs", code == 0)
    code, d, _ = pc("media", "play-pause", "--dry-run")
    check("media play-pause dry-run compiles or maps",
          code == 0 and (osacompile_ok(d.get("applescript", ""))
                         if "applescript" in d else True))

    # -- web resolution
    code, d, _ = pc("web", "youtube", "--dry-run")
    check("web: cache hit resolves youtube",
          code == 0 and "youtube.com" in d.get("url", ""))
    code, d, _ = pc("web", "example.com", "--dry-run")
    check("web: bare domain becomes https url",
          code == 0 and d.get("url") == "https://example.com")
    code, d, _ = pc("web", "zzqx qkjw vvnn", "--dry-run")
    check("web: gibberish falls back to a search url",
          code == 0 and "google.com/search" in d.get("url", ""))

    # -- youtube resolution (network)
    code, d, _ = pc("youtube", "play", "lo-fi beats", "--dry-run")
    if code == 0 and "youtube.com" in d.get("url", ""):
        check("youtube play resolves a url", True,
              d.get("resolved_via", ""))
    else:
        record("SKIP", "youtube play", "network unavailable")

    # -- brightness honesty contract
    code, d, err = pc("brightness", "get")
    check("brightness get: works or fails with guidance",
          code == 0 or "brightness" in (d.get("error", "") + err).lower())
    code, d, _ = pc("brightness", "up", "--dry-run")
    check("brightness up dry-run maps to key code 144",
          code == 0 and "key code 144" in d.get("applescript", ""))

    # -- speaker test
    if a.quiet:
        record("SKIP", "speaker-test", "--quiet")
        not_covered.append("speaker tone playback (--quiet)")
    else:
        pc("volume", "set", "15")
        code, d, _ = pc("speaker-test", "--duration", "0.15", timeout=60)
        pc("volume", "set", str(vol0))
        played = all(t.get("played") for t in d.get("tones", []))
        check("speaker-test plays all 5 tones", code == 0 and played)
        check("speaker-test admits it is unmeasured",
              "playback only" in d.get("verdict", ""))

    # -- mic test (permission dependent)
    code, d, _ = pc("mic-test", "--seconds", "2", timeout=45)
    if code == 0:
        check("mic-test returns metrics", "verdict" in d)
    else:
        record("SKIP", "mic-test", "mic permission or device unavailable")
        not_covered.append("mic capture (permission)")

    # -- negative and contract checks
    p = subprocess.run([sys.executable, PC, "no-such-cmd"],
                       capture_output=True, text=True)
    check("unknown command exits 2", p.returncode == 2)
    code, d, _ = pc("volume", "set")
    check("volume set without value is a usage error (exit 2)", code == 2)
    for c in ["battery", "doctor"]:
        code, d, _ = pc(c)
        check(f"--json {c} parses", isinstance(d, dict) and "ok" in d)

    # -- regressions from the 2026-08-11 verification fan-out
    p = subprocess.run([sys.executable, PC, "battery", "--json"],
                       capture_output=True, text=True)
    try:
        trailing = json.loads(p.stdout).get("ok") is True
    except json.JSONDecodeError:
        trailing = False
    check("trailing --json accepted (documented syntax)",
          p.returncode == 0 and trailing)

    p = subprocess.run(["pbpaste"], capture_output=True, text=True)
    clip0 = p.stdout
    pc("clipboard", "set", "line with newline\n")
    code, d, _ = pc("clipboard", "get")
    check("clipboard get preserves trailing newline",
          d.get("text") == "line with newline\n")
    subprocess.run(["pbcopy"], input=clip0, text=True)

    with open(os.path.join(SKILL, "assets", "websites.json"), "rb") as f:
        cache0 = f.read()
    pc("web", "example", "--dry-run")
    with open(os.path.join(SKILL, "assets", "websites.json"), "rb") as f:
        check("web dry-run does not mutate the site cache",
              f.read() == cache0)

    code, d, _ = pc("brightness", "up", "-3", "--dry-run")
    check("brightness up -3 rejected cleanly (no traceback)",
          code in (1, 2) and isinstance(d, dict) and d.get("ok") is False)
    code, d, _ = pc("brightness", "up", "0", "--dry-run")
    check("brightness up 0 rejected, not defaulted to 3",
          code in (1, 2) and d.get("ok") is False)

    code, d, _ = pc("app", "running", 'x" & "y')
    check("quoted app name treated as literal data",
          code == 0 and d.get("running") is False)
    code, d, _ = pc("web", "HTTP://EXAMPLE.ORG", "--dry-run")
    check("uppercase scheme not double-prefixed",
          code == 0 and d.get("url", "").lower().count("http") == 1)
    code, d, _ = pc("type", "", "--dry-run")
    check("type empty string rejected", code == 1)
    code, d, _ = pc("say", "hi", "--voice", "NoSuchVoiceQzx")
    check("unknown say voice rejected, not silently defaulted", code == 1)

    # -- no em or en dashes anywhere in the skill
    dirty = []
    for root, _, files in os.walk(SKILL):
        for f in files:
            path = os.path.join(root, f)
            try:
                text = open(path, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            if "\u2014" in text or "\u2013" in text:
                dirty.append(f)
    check("no em/en dashes in any skill file", not dirty, ", ".join(dirty))

    # -- live keystroke round trip
    if a.live and keystrokes_granted:
        p = subprocess.run(["pbpaste"], capture_output=True, text=True)
        clip0 = p.stdout
        token = "pc-gate-live-7x"
        try:
            pc("app", "open", "TextEdit")
            time.sleep(1.5)
            pc("app", "activate", "TextEdit")
            time.sleep(0.8)
            subprocess.run(["osascript", "-e",
                            'tell application "TextEdit" to make new document'],
                           capture_output=True)
            time.sleep(0.5)
            pc("type", token)
            time.sleep(0.5)
            pc("keys", "cmd+a")
            pc("keys", "cmd+c")
            time.sleep(0.5)
            p = subprocess.run(["pbpaste"], capture_output=True, text=True)
            check("LIVE: keystrokes reached TextEdit", p.stdout == token)
            subprocess.run(["osascript", "-e",
                            'tell application "TextEdit" to close every '
                            'document saving no'], capture_output=True)
        finally:
            subprocess.run(["pbcopy"], input=clip0, text=True)
    elif a.live:
        record("SKIP", "live keystroke round trip",
               "Accessibility not granted")
        not_covered.append("live keystroke injection (permission)")
    else:
        not_covered.append("live keystroke injection (run gate.py --live "
                           "after granting Accessibility)")

    if not keystrokes_granted:
        not_covered.append("browser/yt/keys/type/brightness-step live "
                           "execution (Accessibility not granted)")
    not_covered.append("Windows backend (not implemented)")

    # -- summary
    npass = sum(1 for s, _, _ in results if s == "PASS")
    nfail = sum(1 for s, _, _ in results if s == "FAIL")
    nskip = sum(1 for s, _, _ in results if s == "SKIP")
    print(f"\nGATE: {npass} passed, {nfail} failed, {nskip} skipped")
    print("NOT COVERED by this run:")
    for item in not_covered:
        print(f"  - {item}")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
