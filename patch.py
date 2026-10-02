#!/usr/bin/env python3
"""Offline, version-checked startup fix for Sengoku Rance on SteamOS/Linux.

Only the patcher is distributed. Users must supply their own game installation.
SPDX-License-Identifier: MIT
"""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

VERSION = "0.1.0"
APP_ID = "3867170"
GAME_NAME = "Sengoku Rance"
EXE_NAME = "Rance7.exe"
EXE_SIZE = 354816
ORIGINAL_SHA256 = "4c4f50aefb1510aa0d2aebee22f54d38813a713989059a0ef4de74f66e893ab5"
PATCHED_SHA256 = "126b8e6fcda30fff82d8fad1e34e27c5cbe3f3257c4255c3a669870b0c550556"
OFFSETS = (0x22742, 0x2277D)
ORIGINAL_INSTRUCTION = bytes.fromhex("68 98 d6 00 00")
PATCHED_INSTRUCTION = bytes.fromhex("68 a8 03 00 00")
BACKUP_DIR = ".rance-proton-fix"
BACKUP_NAME = "Rance7.original.exe"


class PatchError(Exception):
    """An actionable error that should not produce a traceback for users."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identify(data):
    if len(data) != EXE_SIZE:
        return "unsupported"
    return {ORIGINAL_SHA256: "original", PATCHED_SHA256: "patched"}.get(
        digest(data), "unsupported"
    )


def transform(data, restore=False):
    expected = "patched" if restore else "original"
    if identify(data) != expected:
        raise PatchError("Unsupported executable. No changes made; this version needs review.")
    before, after = ORIGINAL_INSTRUCTION, PATCHED_INSTRUCTION
    if restore:
        before, after = after, before
    result = bytearray(data)
    for offset in OFFSETS:
        if result[offset:offset + len(before)] != before:
            raise PatchError("Instruction verification failed. No changes made.")
        result[offset:offset + len(after)] = after
    result = bytes(result)
    if identify(result) != ("original" if restore else "patched"):
        raise PatchError("Output verification failed. No changes made.")
    return result


def read_executable(path):
    # Refuse links, devices and unusually large inputs before reading any data.
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != EXE_SIZE:
            raise PatchError(f"Unsupported file size or type: {path}")
        return stream.read(EXE_SIZE + 1)


def parse_vdf(text):
    """Parse Steam's quoted text VDF, including comments and escaped paths."""
    token_re = re.compile(r'\s+|//[^\n]*|"((?:[^"\\]|\\.)*)"|([{}])')
    tokens = []
    pos = 0
    while pos < len(text):
        match = token_re.match(text, pos)
        if not match:
            raise ValueError("Malformed Steam VDF")
        pos = match.end()
        if match.group(1) is not None:
            tokens.append(("string", re.sub(r'\\([\\"])', r'\1', match.group(1))))
        elif match.group(2):
            tokens.append((match.group(2), match.group(2)))
    cursor = 0

    def object_(nested=False):
        nonlocal cursor
        result = {}
        while cursor < len(tokens):
            kind, key = tokens[cursor]
            cursor += 1
            if kind == "}" and nested:
                return result
            if kind != "string" or cursor >= len(tokens):
                raise ValueError("Malformed Steam VDF object")
            kind, value = tokens[cursor]
            cursor += 1
            if kind == "{":
                result[key] = object_(True)
            elif kind == "string":
                result[key] = value
            else:
                raise ValueError("Malformed Steam VDF value")
        if nested:
            raise ValueError("Unclosed Steam VDF object")
        return result

    return object_()


def read_vdf(path):
    try:
        return parse_vdf(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError):
        return {}


def discover_games(home=None, media_root=None):
    home = Path.home() if home is None else Path(home)
    media_root = Path("/run/media") if media_root is None else Path(media_root)
    roots = [home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root",
             home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    libraries = set(roots)
    for root in roots:
        for config in (root / "steamapps/libraryfolders.vdf", root / "config/libraryfolders.vdf"):
            folders = read_vdf(config).get("libraryfolders", {})
            if not isinstance(folders, dict):
                continue
            for key, entry in folders.items():
                value = entry.get("path") if isinstance(entry, dict) else entry
                if key.isdigit() and isinstance(value, str) and Path(value).is_absolute():
                    libraries.add(Path(value))
    # Support both current and older Steam Deck microSD mount layouts.
    for pattern in ("*/steamapps", "*/*/steamapps"):
        libraries.update(path.parent for path in media_root.glob(pattern))
    found = set()
    for library in libraries:
        apps = library / "steamapps"
        manifest = read_vdf(apps / f"appmanifest_{APP_ID}.acf").get("AppState", {})
        name = GAME_NAME
        if isinstance(manifest, dict) and manifest.get("appid") == APP_ID:
            proposed = manifest.get("installdir", name)
            if isinstance(proposed, str) and proposed not in ("", ".", "..") and Path(proposed).name == proposed:
                name = proposed
        game = apps / "common" / name
        if (game / EXE_NAME).is_file():
            found.add(game.resolve())
    return sorted(found)


def game_path(explicit=None):
    if explicit:
        game = Path(explicit).expanduser().resolve()
        if not (game / EXE_NAME).is_file():
            raise PatchError(f"{EXE_NAME} was not found in {game}")
        return game
    games = discover_games()
    if len(games) == 1:
        return games[0]
    if not games:
        raise PatchError("Game not found. Use --game-dir with Steam's Browse local files folder.")
    raise PatchError("Multiple installations found. Choose one with --game-dir:\n" +
                     "\n".join(str(path) for path in games))


def check_game_stopped(proc_root=Path("/proc")):
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text().strip()
        except OSError:
            continue
        if name.casefold() == EXE_NAME.casefold():
            raise PatchError("Close Sengoku Rance in Steam before applying or restoring the fix.")


@contextmanager
def game_lock(game):
    folder = game / BACKUP_DIR
    if folder.is_symlink():
        raise PatchError("Backup directory is a symbolic link. Refusing to write through it.")
    folder.mkdir(exist_ok=True)
    fd = os.open(folder / "patch.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PatchError("Another patcher is using this installation. Try again when it finishes.") from error
        yield
    finally:
        os.close(fd)


def create_backup(path, data, mode):
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    except FileExistsError:
        if digest(read_executable(path)) != ORIGINAL_SHA256:
            raise PatchError("Existing backup is not the supported original. It was not overwritten.")
        return
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    if read_executable(path) != data:
        raise PatchError("Backup verification failed. The game executable has not been changed.")


def replace_executable(path, expected, replacement):
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=".Rance7-patch-", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        if read_executable(temp_path) != replacement:
            raise PatchError("Temporary executable verification failed. No changes made.")
        if read_executable(path) != expected:
            raise PatchError("The executable changed during patching. Retry after Steam finishes updating.")
        os.replace(temp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp_path.unlink(missing_ok=True)


def operate(game, action):
    game = Path(game)
    exe = game / EXE_NAME
    data = read_executable(exe)
    state = identify(data)
    if action == "status":
        descriptions = {"original": "Supported original: startup fix is not applied.",
                        "patched": "Startup fix is already applied.",
                        "unsupported": "Unsupported executable: no changes will be made."}
        return f"{game}\n{descriptions[state]}\nSHA-256: {digest(data)}"
    if action not in ("apply", "restore"):
        raise PatchError("Unknown action.")
    check_game_stopped()
    with game_lock(game):
        data = read_executable(exe)
        state = identify(data)
        if state == "unsupported":
            raise PatchError("Unsupported executable. This may be another language or an updated build.\n"
                             f"No executable or backup was changed. SHA-256: {digest(data)}")
        if (action, state) in (("apply", "patched"), ("restore", "original")):
            return "Already patched. No changes made." if action == "apply" else "Already original. No changes made."
        backup = game / BACKUP_DIR / BACKUP_NAME
        if action == "apply":
            replacement = transform(data)
            create_backup(backup, data, stat.S_IMODE(exe.stat().st_mode))
        else:
            if not backup.exists():
                raise PatchError("Original backup is missing. Use Steam's Verify integrity to restore the game.")
            replacement = read_executable(backup)
            if identify(replacement) != "original":
                raise PatchError("Backup verification failed. Nothing was restored.")
        replace_executable(exe, data, replacement)
        if read_executable(exe) != replacement:
            raise PatchError("Final verification failed. Your original backup is still available.")
        return ("Startup fix applied. Launch from Steam as usual.\n"
                "No special launch options are needed for this fix.\n"
                f"Original backup: {backup}") if action == "apply" else "Original executable restored. Backup kept."


class Dialogs:
    """Optional KDE/Zenity UI; patching itself needs only Python's standard library."""

    def __init__(self):
        self.tool = shutil.which("kdialog") or shutil.which("zenity")
        if not self.tool:
            raise PatchError("No desktop dialog tool found. Run: python3 patch.py apply")
        self.kde = Path(self.tool).name == "kdialog"

    def message(self, text, error=False):
        flag = ("--error" if error else "--msgbox") if self.kde else ("--error" if error else "--info")
        args = [flag, text] if self.kde else [flag, "--text", text, "--no-markup", "--width=520"]
        subprocess.run([self.tool, "--title", "Sengoku Rance startup fix", *args], check=False)

    def confirm(self, text):
        args = ["--yesno", text] if self.kde else ["--question", "--text", text, "--no-markup", "--width=520"]
        return subprocess.run([self.tool, "--title", "Sengoku Rance startup fix", *args], check=False).returncode == 0

    def directory(self):
        args = ["--getexistingdirectory", str(Path.home())] if self.kde else ["--file-selection", "--directory"]
        result = subprocess.run([self.tool, "--title", "Choose the folder containing Rance7.exe", *args],
                                capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""


def run_gui(explicit=None):
    dialogs = Dialogs()
    try:
        games = [game_path(explicit)] if explicit else discover_games()
        if len(games) == 1:
            game = games[0]
        else:
            chosen = dialogs.directory()
            if not chosen:
                return 0
            game = game_path(chosen)
        state = identify(read_executable(game / EXE_NAME))
        if state == "unsupported":
            raise PatchError(operate(game, "status"))
        action = "restore" if state == "patched" else "apply"
        question = ("The startup fix is already applied. Restore the original executable?" if state == "patched"
                    else "Apply the startup fix for the Simplified Chinese Steam build?\nAn original backup will be kept.")
        if dialogs.confirm(f"{game}\n\n{question}\n\nClose the game first."):
            dialogs.message(operate(game, action))
        return 0
    except (PatchError, OSError) as error:
        dialogs.message(str(error), error=True)
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("status", "apply", "restore"), default="status")
    parser.add_argument("--game-dir", help="Folder containing Rance7.exe; auto-detected when omitted")
    parser.add_argument("--gui", action="store_true", help="Use KDE or Zenity desktop dialogs")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)
    try:
        if args.gui:
            if args.action != "status":
                parser.error("--gui chooses the action interactively; omit the action argument")
            return run_gui(args.game_dir)
        print(operate(game_path(args.game_dir), args.action))
        return 0
    except (PatchError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
