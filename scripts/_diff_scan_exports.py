import json
import sys


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    if len(args) < 3:
        print("usage: _diff_scan_exports.py before.json after.json", file=sys.stderr)
        return 2
    before_path, after_path = args[1], args[2]

    with open(before_path, encoding="utf-8") as f:
        before = json.load(f)
    with open(after_path, encoding="utf-8") as f:
        after = json.load(f)

    def by_name(data):
        return {d["device_name"]: d for d in data.get("drivers", [])}

    b, a = by_name(before), by_name(after)
    keys = sorted(set(b) | set(a))

    print("=== Version or status changes ===")
    for k in keys:
        if k not in b or k not in a:
            continue
        if b[k].get("status") != a[k].get("status") or b[k].get("installed_version") != a[k].get(
            "installed_version"
        ):
            print(k)
            print(f"  ver: {b[k].get('installed_version')} -> {a[k].get('installed_version')}")
            print(f"  st:  {b[k].get('status')} -> {a[k].get('status')}")
            print(f"  tier: {b[k].get('tier')} -> {a[k].get('tier')}")

    removed = set(b) - set(a)
    added = set(a) - set(b)
    if removed:
        print("\n=== Removed from export ===")
        for k in sorted(removed):
            print(k, b[k].get("installed_version"), b[k].get("status"))
    if added:
        print("\n=== Added to export ===")
        for k in sorted(added):
            print(k, a[k].get("installed_version"), a[k].get("status"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
