# Catalog layout preset comparison

The mock canvas was removed — comparisons must use the **real BSOD Analyzer window**.

## Interactive (recommended)

From `Desktop\BSODAnalyzer\app`:

```bat
py -3 scripts\catalog_layout_preview.py
```

- Opens the actual app at 1180×780 with sample driver/firmware rows (Realtek dual-line, etc.).
- Use the **status-bar dropdown** to switch presets **A–D**.
- Row counts update live (`Drivers: 3 full + 1 partial`).
- Switch **Drivers** and **Firmware** tabs while comparing.

## PNG comparison sheet (on your PC)

Requires a normal Windows display (not agent/CI):

```bat
py -3 scripts\catalog_layout_preview.py --capture
```

Writes eight PNGs plus `index.html` here, and opens the gallery in your browser.

## After you pick a preset

Reply with the letter (e.g. `D — balanced`) or run:

```bat
py -3 scripts\catalog_layout_preview.py --save balanced
```
