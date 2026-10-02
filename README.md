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

## Undo

Run the launcher again, or use `python3 patch.py restore`. To check the patch, use `python3 patch.py status`.

The patch changes four bytes, checks the executable’s SHA-256, and keeps the original at `.rance-proton-fix/Rance7.original.exe` inside the game folder. Unknown versions are left alone. Steam updates may remove the fix.

Tested on Linux with Proton Experimental. Steam Deck hardware testing is pending. Supports the recognized Simplified Chinese executable from build `25565749`.

MIT licensed. Unofficial project; no game files included.
