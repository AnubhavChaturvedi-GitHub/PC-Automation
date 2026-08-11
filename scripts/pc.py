#!/usr/bin/env python3
"""pc.py: local machine hands for agents. macOS backend, stdlib only.

Every command is non-interactive, takes arguments, exits 0 on success,
1 on runtime failure, 2 on usage error. Add --json for machine-readable
output. Keystroke-emitting commands accept --dry-run to print the
AppleScript instead of executing it.
"""

import argparse
import datetime
import json
import math
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import wave

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES_PATH = os.path.join(SKILL_DIR, "assets", "websites.json")

ACCESSIBILITY_FIX = (
    "Keystroke sending is blocked by macOS. Fix: System Settings > "
    "Privacy & Security > Accessibility > enable the app running this "
    "agent (e.g. Claude or your terminal), then retry."
)


def run(cmd, timeout=30, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def osa(script, timeout=15):
    return run(["osascript", "-e", script], timeout=timeout)


def as_str(s):
    """Escape a value for safe embedding as an AppleScript string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def fail(msg, extra=None):
    out = {"ok": False, "error": msg}
    if extra:
        out.update(extra)
    return out


def usage_fail(msg, extra=None):
    out = fail(msg, extra)
    out["_exit"] = 2
    return out


def ok(data):
    out = {"ok": True}
    out.update(data)
    return out


# ---------- keystroke engine ----------

KEYCODES = {
    "left": 123, "right": 124, "up": 126, "down": 125,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "return": 36, "enter": 36, "esc": 53, "escape": 53,
    "tab": 48, "space": 49, "delete": 51, "forward-delete": 117,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "brightness-up": 144, "brightness-down": 145,
}
CHAR_ALIASES = {
    "comma": ",", "period": ".", "dot": ".", "slash": "/", "minus": "-",
    "plus": "+", "equals": "=", "backslash": "\\", "semicolon": ";",
    "quote": "'", "backtick": "`", "lbracket": "[", "rbracket": "]",
}
MODS = {
    "cmd": "command down", "command": "command down",
    "ctrl": "control down", "control": "control down",
    "alt": "option down", "option": "option down",
    "shift": "shift down",
}


def build_key_script(combo):
    if not combo.strip():
        raise ValueError("empty key combo")
    parts = [p.strip().lower() for p in combo.split("+")]
    if any(p == "" for p in parts):
        raise ValueError("malformed combo: empty segment (use 'plus' for the "
                         "+ key, e.g. cmd+plus)")
    mods, key = parts[:-1], parts[-1]
    bad = [m for m in mods if m not in MODS]
    if bad:
        raise ValueError(f"unknown modifier: {'+'.join(bad)}")
    key = CHAR_ALIASES.get(key, key)
    if key in KEYCODES:
        action = f"key code {KEYCODES[key]}"
    elif len(key) == 1:
        esc = key.replace("\\", "\\\\").replace('"', '\\"')
        action = f'keystroke "{esc}"'
    else:
        raise ValueError(f"unknown key: {key}")
    using = ""
    if mods:
        using = " using {" + ", ".join(MODS[m] for m in mods) + "}"
    return f"tell application \"System Events\" to {action}{using}"


def send_keys(combo, dry_run=False):
    try:
        script = build_key_script(combo)
    except ValueError as e:
        return fail(str(e))
    if dry_run:
        return ok({"dry_run": True, "combo": combo, "applescript": script})
    code, _, err = osa(script)
    if code != 0:
        if "1002" in err or "not allowed to send keystrokes" in err:
            return fail(ACCESSIBILITY_FIX, {"combo": combo})
        return fail(err or "osascript failed", {"combo": combo})
    return ok({"sent": combo})


def type_text(text, dry_run=False):
    if text == "":
        return fail("nothing to type (empty text)")
    script = f'tell application "System Events" to keystroke "{as_str(text)}"'
    if dry_run:
        return ok({"dry_run": True, "applescript": script})
    code, _, err = osa(script)
    if code != 0:
        if "1002" in err or "not allowed to send keystrokes" in err:
            return fail(ACCESSIBILITY_FIX)
        return fail(err or "osascript failed")
    return ok({"typed_chars": len(text)})


# ---------- system ----------

def battery():
    code, out, err = run(["pmset", "-g", "batt"])
    if code != 0:
        return fail(err or "pmset failed")
    m = re.search(r"(\d+)%;\s*([\w\s]+?);", out)
    src = "AC" if "AC Power" in out else "Battery"
    data = {"source": src, "raw": out.splitlines()[-1].strip()}
    if m:
        data["percent"] = int(m.group(1))
        data["state"] = m.group(2).strip()
    t = re.search(r"(\d+:\d+) remaining", out)
    if t:
        data["time_remaining"] = t.group(1)
    return ok(data)


def volume_get():
    code, out, err = osa("get volume settings")
    if code != 0:
        return fail(err)
    vol = re.search(r"output volume:(\d+)", out)
    muted = re.search(r"output muted:(\w+)", out)
    return ok({
        "volume": int(vol.group(1)) if vol else None,
        "muted": muted.group(1) == "true" if muted else None,
    })


def volume_set(n):
    if not 0 <= n <= 100:
        return fail("volume must be 0-100")
    code, _, err = osa(f"set volume output volume {n}")
    if code != 0:
        return fail(err)
    return ok({"volume": n})


def volume_step(delta):
    cur = volume_get()
    if not cur["ok"]:
        return cur
    new = max(0, min(100, cur["volume"] + delta))
    r = volume_set(new)
    if r["ok"]:
        r["previous"] = cur["volume"]
    return r


def volume_mute(state):
    code, _, err = osa(f"set volume output muted {'true' if state else 'false'}")
    if code != 0:
        return fail(err)
    return ok({"muted": state})


def brightness_cli_works():
    if not shutil.which("brightness"):
        return False
    code, out, err = run(["brightness", "-l"])
    return code == 0 and "failed" not in err and "brightness" in out


def brightness_get():
    if brightness_cli_works():
        _, out, _ = run(["brightness", "-l"])
        m = re.search(r"brightness\s+([\d.]+)", out)
        if m:
            return ok({"brightness": float(m.group(1)), "method": "cli"})
    return fail(
        "Absolute brightness read is unavailable on this macOS (the "
        "DisplayServices API was removed). Use 'brightness up/down'."
    )


def brightness_set(value):
    if shutil.which("brightness"):
        code, _, err = run(["brightness", str(value)])
        if code == 0 and "failed" not in err:
            return ok({"brightness": value, "method": "cli"})
    return fail(
        "Absolute brightness set is unavailable on this macOS. "
        "Use 'brightness up [steps]' or 'brightness down [steps]' instead."
    )


def brightness_step(direction, steps, dry_run=False):
    if steps < 1:
        return fail("steps must be a positive integer (1 or more)")
    key = "brightness-up" if direction == "up" else "brightness-down"
    results = []
    for _ in range(steps):
        r = send_keys(key, dry_run=dry_run)
        results.append(r)
        if not r["ok"]:
            return fail(r["error"], {"completed_steps": len(results) - 1})
        if dry_run:
            break
    if dry_run:
        return ok({"dry_run": True, "applescript": results[0]["applescript"],
                   "steps": steps})
    return ok({"direction": direction, "steps": steps, "method": "keycode"})


def ip_info(public=False):
    data = {}
    for iface in ["en0", "en1", "en2"]:
        code, out, _ = run(["ipconfig", "getifaddr", iface])
        if code == 0 and out:
            data["local"] = out
            data["interface"] = iface
            break
    if "local" not in data:
        data["local"] = None
    if public:
        try:
            req = urllib.request.Request(
                "https://checkip.amazonaws.com",
                headers={"User-Agent": "Mozilla/5.0"})
            data["public"] = urllib.request.urlopen(
                req, timeout=6).read().decode().strip()
        except Exception as e:
            data["public"] = None
            data["public_error"] = str(e)
    return ok(data)


# ---------- apps ----------

def apps_list(show_all=False):
    if show_all:
        script = 'tell application "System Events" to get name of every process'
    else:
        script = ('tell application "System Events" to get name of every '
                  'application process whose visible is true')
    code, out, err = osa(script)
    if code != 0:
        return fail(err)
    names = sorted({n.strip() for n in out.split(",") if n.strip()})
    return ok({"count": len(names), "apps": names})


def app_front():
    code, out, err = osa(
        'tell application "System Events" to get name of first application '
        'process whose frontmost is true')
    if code != 0:
        return fail(err)
    return ok({"frontmost": out})


def app_running(name):
    code, out, err = osa(
        f'tell application "System Events" to (name of processes) '
        f'contains "{as_str(name)}"')
    if code != 0:
        return fail(err)
    return ok({"app": name, "running": out == "true"})


def app_open(name):
    code, _, err = run(["open", "-a", name])
    if code != 0:
        return fail(f"could not open '{name}': {err}")
    return ok({"opened": name})


def app_quit(name):
    r = app_running(name)
    if r["ok"] and not r["running"]:
        return ok({"app": name, "was_running": False})
    code, _, err = osa(f'tell application "{as_str(name)}" to quit')
    if code != 0:
        return fail(err)
    return ok({"quit": name, "was_running": True})


def app_activate(name):
    code, _, err = osa(f'tell application "{as_str(name)}" to activate')
    if code != 0:
        return fail(err)
    return ok({"activated": name})


# ---------- web ----------

def load_sites():
    try:
        with open(SITES_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_sites(sites):
    with open(SITES_PATH, "w") as f:
        json.dump(sites, f, indent=2, sort_keys=True)


def normalize_url(u):
    if not re.match(r"^[a-z]+://", u, re.I):
        u = "https://" + u
    return u


def url_reachable(url):
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        urllib.request.urlopen(req, timeout=5)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def web_open(name, dry_run=False):
    name = name.strip()
    sites = load_sites()
    key = name.lower()
    if re.match(r"^[a-z]+://", key, re.I) or ("." in key and " " not in key):
        url, source = normalize_url(name), "url"
    elif key in sites:
        url, source = normalize_url(sites[key]), "cache"
    elif key.replace(" ", "") in sites:
        url, source = normalize_url(sites[key.replace(" ", "")]), "cache"
    else:
        guess = "https://" + key.replace(" ", "") + ".com"
        if url_reachable(guess):
            url, source = guess, "guess"
            if not dry_run:  # a dry-run must not mutate the cache
                sites[key] = guess
                save_sites(sites)
        else:
            url = ("https://www.google.com/search?q="
                   + urllib.parse.quote(name))
            source = "search-fallback"
    if dry_run:
        return ok({"dry_run": True, "url": url, "resolved_via": source})
    code, _, err = run(["open", url])
    if code != 0:
        return fail(err)
    return ok({"opened": url, "resolved_via": source})


def youtube_play(query, dry_run=False):
    search_url = ("https://www.youtube.com/results?search_query="
                  + urllib.parse.quote(query))
    url, source = search_url, "search-page"
    try:
        req = urllib.request.Request(
            search_url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=8).read().decode(
            "utf-8", "ignore")
        m = re.search(r'"videoId":"([\w-]{11})"', html)
        if m:
            url = "https://www.youtube.com/watch?v=" + m.group(1)
            source = "first-result"
    except Exception:
        pass
    if dry_run:
        return ok({"dry_run": True, "url": url, "resolved_via": source})
    code, _, err = run(["open", url])
    if code != 0:
        return fail(err)
    return ok({"opened": url, "resolved_via": source})


# ---------- browser / youtube-transport / media ----------

BROWSER_KEYS = {
    "new-tab": "cmd+t", "close-tab": "cmd+w", "reopen-tab": "cmd+shift+t",
    "next-tab": "ctrl+tab", "prev-tab": "ctrl+shift+tab",
    "new-window": "cmd+n", "private-window": "cmd+shift+n",
    "zoom-in": "cmd+plus", "zoom-out": "cmd+minus", "zoom-reset": "cmd+0",
    "refresh": "cmd+r", "hard-refresh": "cmd+shift+r",
    "back": "cmd+lbracket", "forward": "cmd+rbracket",
    "history": "cmd+y", "bookmarks": "cmd+alt+b",
    "address-bar": "cmd+l", "find": "cmd+f",
    "devtools": "cmd+alt+i", "fullscreen": "ctrl+cmd+f",
}

YT_KEYS = {
    "play-pause": "k", "mute": "m", "fullscreen": "f", "theater": "t",
    "miniplayer": "i", "captions": "c",
    "vol-up": "up", "vol-down": "down",
    "back-5": "left", "fwd-5": "right",
    "back-10": "j", "fwd-10": "l",
    "prev-frame": "comma", "next-frame": "period",
    "speed-up": "shift+period", "speed-down": "shift+comma",
    "start": "home", "end": "end",
    "prev-chapter": "ctrl+left", "next-chapter": "ctrl+right",
    "next-video": "shift+n", "prev-video": "shift+p",
}


def browser_action(action, dry_run=False):
    if action not in BROWSER_KEYS:
        return fail(f"unknown browser action '{action}'. "
                    f"Options: {', '.join(sorted(BROWSER_KEYS))}")
    r = send_keys(BROWSER_KEYS[action], dry_run=dry_run)
    if r["ok"]:
        r["action"] = action
    return r


def yt_action(action, dry_run=False):
    if action not in YT_KEYS:
        return fail(f"unknown yt action '{action}'. "
                    f"Options: {', '.join(sorted(YT_KEYS))}")
    r = send_keys(YT_KEYS[action], dry_run=dry_run)
    if r["ok"]:
        r["action"] = action
        r["note"] = "sent to the frontmost app; focus a browser with YouTube first"
    return r


PLAYERS = ["Spotify", "Music"]


def scriptable_player():
    for p in PLAYERS:
        r = app_running(p)
        if r["ok"] and r["running"]:
            return p
    return None


def media_action(action, dry_run=False):
    player = scriptable_player()
    if player:
        cmds = {"play-pause": "playpause", "next": "next track",
                "prev": "previous track", "play": "play", "pause": "pause"}
        if action == "status":
            code, out, err = osa(
                f'tell application "{player}" to get player state as string')
            if code != 0:
                return fail(err)
            data = {"player": player, "state": out}
            code, out, _ = osa(
                f'tell application "{player}" to get name of current track')
            if code == 0:
                data["track"] = out
                code, out, _ = osa(
                    f'tell application "{player}" to get artist of current track')
                if code == 0:
                    data["artist"] = out
            return ok(data)
        if action not in cmds:
            return fail(f"unknown media action '{action}'")
        script = f'tell application "{player}" to {cmds[action]}'
        if dry_run:
            return ok({"dry_run": True, "player": player, "action": action,
                       "applescript": script})
        code, _, err = osa(script)
        if code != 0:
            return fail(err)
        return ok({"player": player, "action": action})
    if action == "status":
        r = app_front()
        front = r.get("frontmost") if r["ok"] else None
        return ok({"player": None, "frontmost": front,
                   "note": "no scriptable player (Spotify/Music) running"})
    fallback = {"play-pause": "space", "play": "space", "pause": "space",
                "next": "shift+n", "prev": "shift+p"}
    if action not in fallback:
        return fail(f"unknown media action '{action}'")
    r = send_keys(fallback[action], dry_run=dry_run)
    if r["ok"]:
        r["action"] = action
        r["note"] = ("no scriptable player; " + ("would send keys to"
                     if dry_run else "sent keys to") + " the frontmost app")
    return r


# ---------- desktop utilities ----------

def screenshot(path=None):
    if not path:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.expanduser(f"~/Desktop/pc-screenshot-{stamp}.png")
    path = os.path.expanduser(path)
    parent = os.path.dirname(path) or "."
    if not os.path.isdir(parent):
        return fail(f"destination directory does not exist: {parent}")
    code, _, err = run(["screencapture", "-x", path])
    if code != 0 or (err and "cannot write" in err):
        return fail(err or "screencapture failed")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return fail("screencapture produced no file (Screen Recording "
                    "permission may be missing for this app)")
    return ok({"path": path, "bytes": os.path.getsize(path)})


def clipboard_get():
    # Do not use run(): it strips, which corrupts whitespace-significant
    # clipboard content (trailing newlines, indented code, padded text).
    p = subprocess.run(["pbpaste"], capture_output=True, text=True)
    if p.returncode != 0:
        return fail(p.stderr.strip() or "pbpaste failed")
    return ok({"text": p.stdout})


def clipboard_set(text):
    p = subprocess.run(["pbcopy"], input=text, text=True)
    if p.returncode != 0:
        return fail("pbcopy failed")
    return ok({"copied_chars": len(text)})


def notify(message, title="pc-control", subtitle=None):
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    if subtitle:
        script += f' subtitle "{esc(subtitle)}"'
    code, _, err = osa(script)
    if code != 0:
        return fail(err)
    return ok({"notified": message})


def say_text(text, voice=None):
    cmd = ["say"]
    if voice:
        # `say` silently falls back to the default voice for an unknown name
        # and still exits 0, so validate against the installed voice list.
        _, out, _ = run(["say", "-v", "?"])
        names = {ln.split()[0] for ln in out.splitlines() if ln.strip()}
        if voice not in names:
            return fail(f"unknown voice '{voice}'. List them with: say -v '?'")
        cmd += ["-v", voice]
    cmd.append(text)
    code, _, err = run(cmd, timeout=120)
    if code != 0:
        return fail(err)
    return ok({"spoke_chars": len(text)})


# ---------- hardware tests ----------

def read_wav_frames(path, frame_ms=20):
    with wave.open(path, "rb") as w:
        rate, n = w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    samples = struct.unpack(f"<{len(raw)//2}h", raw)
    per = max(1, int(rate * frame_ms / 1000))
    frames = [samples[i:i + per] for i in range(0, len(samples), per)]
    rms = [math.sqrt(sum(s * s for s in f) / len(f)) for f in frames if f]
    peak = max((abs(s) for s in samples), default=0)
    clip = sum(1 for s in samples if abs(s) >= 32700) / max(1, len(samples))
    return rms, peak, clip


def mic_test(seconds=5):
    if not shutil.which("ffmpeg"):
        return fail("ffmpeg is required for mic-test (brew install ffmpeg)")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    code, _, err = run(
        ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":0",
         "-t", str(seconds), "-ar", "44100", "-ac", "1", tmp.name],
        timeout=seconds + 20)
    if code != 0 or not os.path.getsize(tmp.name):
        os.unlink(tmp.name)
        return fail(
            "mic capture failed (microphone permission for this app, or no "
            "input device). ffmpeg said: " + err.splitlines()[-1] if err else
            "mic capture failed")
    rms, peak, clip = read_wav_frames(tmp.name)
    os.unlink(tmp.name)
    if not rms:
        return fail("no audio frames captured")
    srt = sorted(rms)
    noise = srt[int(len(srt) * 0.10)]
    signal = srt[int(len(srt) * 0.95) - 1]
    snr = 20 * math.log10(signal / noise) if noise > 0 else float("inf")
    verdict = "ok"
    if peak < 100:
        verdict = "silent: mic dead, muted, or permission denied"
    elif clip > 0.05:
        verdict = "clipping: input gain too high"
    elif snr < 6:
        verdict = "noisy: little dynamic range between noise floor and signal"
    return ok({"seconds": seconds, "peak": peak,
               "clipping_pct": round(clip * 100, 2),
               "noise_floor_rms": round(noise, 1),
               "signal_rms": round(signal, 1),
               "snr_db": round(snr, 1) if snr != float("inf") else None,
               "verdict": verdict})


def write_tone(path, freq, seconds, rate=44100, amp=0.4):
    n = int(rate * seconds)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            if freq == "sweep":
                f = 200 * (10 ** (i / n * 1.7))
                v = math.sin(2 * math.pi * f * i / rate)
            else:
                v = math.sin(2 * math.pi * freq * i / rate)
            frames += struct.pack("<h", int(v * amp * 32767))
        w.writeframes(bytes(frames))


def speaker_test(measure=False, duration=1.0):
    tones = [100, 1000, 5000, 10000, "sweep"]
    results = []
    for freq in tones:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        write_tone(tmp.name, freq, duration)
        label = f"{freq}Hz" if freq != "sweep" else "sweep-200-10k"
        if measure and shutil.which("ffmpeg"):
            rec = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            rec.close()
            recorder = subprocess.Popen(
                ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":0",
                 "-t", str(duration + 0.5), "-ar", "44100", "-ac", "1",
                 rec.name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            run(["afplay", tmp.name], timeout=duration + 10)
            recorder.wait(timeout=duration + 15)
            heard = None
            if os.path.exists(rec.name) and os.path.getsize(rec.name):
                rms, peak, _ = read_wav_frames(rec.name)
                heard = peak > 500
                os.unlink(rec.name)
            results.append({"tone": label, "played": True, "heard": heard})
        else:
            code, _, err = run(["afplay", tmp.name], timeout=duration + 10)
            results.append({"tone": label, "played": code == 0})
        os.unlink(tmp.name)
    data = {"tones": results, "measured": measure}
    if measure:
        heard = [r for r in results if r.get("heard")]
        data["verdict"] = (f"{len(heard)}/{len(results)} tones confirmed "
                           "through the microphone")
    else:
        data["verdict"] = ("playback only: tones were sent to the speaker "
                           "but not verified. Use --measure to confirm "
                           "through the microphone.")
    return ok(data)


# ---------- doctor ----------

def doctor():
    checks = {}
    checks["platform"] = f"{platform.system()} {platform.mac_ver()[0]}"
    checks["osascript"] = bool(shutil.which("osascript"))
    code, out, _ = osa('tell application "System Events" to count processes')
    checks["system_events_query"] = code == 0
    code, _, err = osa('tell application "System Events" to key up shift')
    checks["keystrokes"] = code == 0
    if not checks["keystrokes"]:
        checks["keystrokes_fix"] = ACCESSIBILITY_FIX
    checks["brightness_cli"] = brightness_cli_works()
    if shutil.which("brightness") and not checks["brightness_cli"]:
        checks["brightness_note"] = ("brightness CLI installed but broken on "
                                     "this macOS; brightness up/down uses key "
                                     "codes and needs the Accessibility grant")
    checks["ffmpeg"] = bool(shutil.which("ffmpeg"))
    try:
        req = urllib.request.Request(
            "https://checkip.amazonaws.com",
            headers={"User-Agent": "Mozilla/5.0"})
        urllib.request.urlopen(req, timeout=5)
        checks["network"] = True
    except Exception:
        checks["network"] = False
    caps_ok = [k for k, v in checks.items() if v is True]
    caps_bad = [k for k, v in checks.items() if v is False]
    return ok({"checks": checks, "working": caps_ok, "blocked": caps_bad})


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(prog="pc", description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("battery")
    sub.add_parser("doctor")

    p = sub.add_parser("volume")
    p.add_argument("action", choices=["get", "set", "up", "down", "mute", "unmute"])
    p.add_argument("value", nargs="?", type=int)

    p = sub.add_parser("brightness")
    p.add_argument("action", choices=["get", "set", "up", "down"])
    p.add_argument("value", nargs="?", type=float)
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("ip")
    p.add_argument("--public", action="store_true")

    p = sub.add_parser("apps")
    p.add_argument("--all", action="store_true")

    p = sub.add_parser("app")
    p.add_argument("action", choices=["open", "quit", "front", "running", "activate"])
    p.add_argument("name", nargs="?")

    p = sub.add_parser("web")
    p.add_argument("name", nargs="+")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("youtube")
    p.add_argument("action", choices=["play", "search"])
    p.add_argument("query", nargs="+")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("browser")
    p.add_argument("action")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("yt")
    p.add_argument("action")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("media")
    p.add_argument("action", choices=["status", "play-pause", "play", "pause",
                                      "next", "prev"])
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("keys")
    p.add_argument("combo")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("type")
    p.add_argument("text")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("screenshot")
    p.add_argument("path", nargs="?")

    p = sub.add_parser("clipboard")
    p.add_argument("action", choices=["get", "set"])
    p.add_argument("text", nargs="?")

    p = sub.add_parser("notify")
    p.add_argument("message")
    p.add_argument("--title", default="pc-control")
    p.add_argument("--subtitle")

    p = sub.add_parser("say")
    p.add_argument("text")
    p.add_argument("--voice")

    p = sub.add_parser("mic-test")
    p.add_argument("--seconds", type=int, default=5)

    p = sub.add_parser("speaker-test")
    p.add_argument("--measure", action="store_true")
    p.add_argument("--duration", type=float, default=1.0)

    # accept --json in trailing position too, as the docs show
    for sp in sub.choices.values():
        sp.add_argument("--json", action="store_true", dest="json",
                        default=argparse.SUPPRESS)

    a = ap.parse_args()

    if a.cmd == "battery":
        r = battery()
    elif a.cmd == "doctor":
        r = doctor()
    elif a.cmd == "volume":
        if a.action == "get":
            r = volume_get()
        elif a.action == "set":
            r = volume_set(a.value) if a.value is not None else usage_fail(
                "volume set needs a value 0-100")
        elif a.action == "up":
            r = volume_step(a.value if a.value is not None else 10)
        elif a.action == "down":
            r = volume_step(-(a.value if a.value is not None else 10))
        else:
            r = volume_mute(a.action == "mute")
    elif a.cmd == "brightness":
        if a.action == "get":
            r = brightness_get()
        elif a.action == "set":
            r = brightness_set(a.value) if a.value is not None else usage_fail(
                "brightness set needs a value 0.0-1.0")
        elif a.value is not None and not float(a.value).is_integer():
            r = usage_fail("steps must be a whole number")
        else:
            steps = 3 if a.value is None else int(a.value)
            r = brightness_step(a.action, steps, dry_run=a.dry_run)
    elif a.cmd == "ip":
        r = ip_info(public=a.public)
    elif a.cmd == "apps":
        r = apps_list(show_all=a.all)
    elif a.cmd == "app":
        if a.action == "front":
            r = app_front()
        elif not a.name:
            r = usage_fail(f"app {a.action} needs an app name")
        elif a.action == "open":
            r = app_open(a.name)
        elif a.action == "quit":
            r = app_quit(a.name)
        elif a.action == "running":
            r = app_running(a.name)
        else:
            r = app_activate(a.name)
    elif a.cmd == "web":
        r = web_open(" ".join(a.name), dry_run=a.dry_run)
    elif a.cmd == "youtube":
        q = " ".join(a.query)
        if a.action == "play":
            r = youtube_play(q, dry_run=a.dry_run)
        else:
            url = ("https://www.youtube.com/results?search_query="
                   + urllib.parse.quote(q))
            if a.dry_run:
                r = ok({"dry_run": True, "url": url,
                        "resolved_via": "search-page"})
            else:
                code, _, err = run(["open", url])
                r = (ok({"opened": url, "resolved_via": "search-page"})
                     if code == 0 else fail(err))
    elif a.cmd == "browser":
        r = browser_action(a.action, dry_run=a.dry_run)
    elif a.cmd == "yt":
        r = yt_action(a.action, dry_run=a.dry_run)
    elif a.cmd == "media":
        r = media_action(a.action, dry_run=a.dry_run)
    elif a.cmd == "keys":
        r = send_keys(a.combo, dry_run=a.dry_run)
    elif a.cmd == "type":
        r = type_text(a.text, dry_run=a.dry_run)
    elif a.cmd == "screenshot":
        r = screenshot(a.path)
    elif a.cmd == "clipboard":
        if a.action == "get":
            r = clipboard_get()
        else:
            r = clipboard_set(a.text) if a.text is not None else usage_fail(
                "clipboard set needs text")
    elif a.cmd == "notify":
        r = notify(a.message, title=a.title, subtitle=a.subtitle)
    elif a.cmd == "say":
        r = say_text(a.text, voice=a.voice)
    elif a.cmd == "mic-test":
        r = mic_test(seconds=a.seconds)
    elif a.cmd == "speaker-test":
        r = speaker_test(measure=a.measure, duration=a.duration)
    else:
        r = fail("unknown command")

    exit_code = 0 if r["ok"] else r.pop("_exit", 1)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        if r["ok"]:
            for k, v in r.items():
                if k != "ok":
                    print(f"{k}: {v}")
        else:
            print(f"error: {r['error']}", file=sys.stderr)
            for k, v in r.items():
                if k not in ("ok", "error"):
                    print(f"{k}: {v}", file=sys.stderr)
    sys.exit(exit_code)


if __name__ == "__main__":
    if platform.system() != "Darwin":
        print("error: this backend supports macOS only", file=sys.stderr)
        sys.exit(1)
    main()
