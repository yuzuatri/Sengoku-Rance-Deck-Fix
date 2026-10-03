# Sengoku Rance Deck Fix

A small fix for the **Steam Simplified Chinese version** when Steam says the game is running but no window opens.

## Use

1. Close the game and let Steam finish any updates.
2. Download and extract the ZIP. On Steam Deck, switch to Desktop Mode.
3. Run `launch.sh` and confirm Apply. If needed, mark it executable in Properties → Permissions.
4. Start the game normally through Steam. No special launch options needed.

Requires Python 3.9+. If the launcher doesn’t open, run this in the extracted folder:

```sh
python3 patch.py apply
```

If the game isn’t found, add `--game-dir "/path/to/Sengoku Rance"`.

## Optional SimHei font

Place your own `simhei.ttf` beside `patch.py`, then run the launcher or `python3 patch.py apply`. It also works if the startup fix is already applied. The launcher offers font installation before the restore option.

The font is copied into this game’s `steamapps/compatdata/3867170/pfx/drive_c/windows/Fonts/` folder. Existing fonts are kept. Launch the game once through Steam first so its Proton folder exists; for a custom location, add `--proton-prefix "/path/to/pfx"`. Restart the game afterward. Installing the font makes it available; it doesn’t force the game to use it.

The font file is not included in the download. Use a copy you are licensed to install.

## Undo

Run the launcher again, or use `python3 patch.py restore`. To check the patch, use `python3 patch.py status`.

Restore only undoes the executable patch. To remove a font installed by this tool, delete `simhei.ttf` from that game’s Proton `Fonts` folder.

The patch changes four bytes, checks the executable’s SHA-256, and keeps the original at `.rance-proton-fix/Rance7.original.exe` inside the game folder. Unknown versions are left alone. Steam updates may remove the fix.

Tested on Linux with Proton Experimental. Steam Deck hardware testing is pending. Supports the recognized Simplified Chinese executable from build `25565749`.

MIT licensed. Unofficial project; no game files included.
