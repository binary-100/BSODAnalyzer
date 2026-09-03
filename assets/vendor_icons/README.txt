Vendor icon overrides (optional)
================================

The Drivers and Firmware tabs show a brand-colored monogram badge when the app can
identify a manufacturer (AMD, NVIDIA, Intel, Dell, Samsung, etc.).

To use your own logo artwork instead of the monogram, drop a file here named after
the vendor key:

  assets/vendor_icons/{vendor_key}.svg
  assets/vendor_icons/{vendor_key}.png

Examples:
  amd.svg       — AMD devices / chipset drivers
  nvidia.svg    — GeForce drivers
  intel.svg     — Intel graphics, network, chipset
  dell.svg      — Dell OEM devices
  samsung.svg   — Samsung SSDs
  western_digital.svg — WD storage

Supported keys match device_enrichment vendor keys (lowercase), plus firmware keys
like firmware, storage, western_digital, seagate, crucial.

SVG is preferred (scales cleanly at 22px list rows and 48px inspector headers).
The app does not bundle official trademark logos; monograms are used by default so
you can optionally supply licensed artwork in this folder.

When building with PyInstaller, this folder is bundled automatically if present.
