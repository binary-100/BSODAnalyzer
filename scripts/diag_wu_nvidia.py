import sys

from pathlib import Path



sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import driver_catalog as dc



ctx = {

    "pnp_class": "display",

    "device_label": "NVIDIA GeForce",

    "video_controllers": [{"pnp_device_id": r"PCI\VEN_10DE&DEV_24E0&SUBSYS_0B5C1028"}],

}

hit, method = dc._nvidia_lookup_download_info(ctx)

print("lookup method:", method or "(none)")

if hit:

    print("version:", hit.get("Version"))

    print("release:", hit.get("ReleaseDateTime"))

else:

    print("lookup failed")

