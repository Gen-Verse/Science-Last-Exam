"""Add the standard Proxima Centauri name to HIP 70890 in older Celestia data."""
import argparse
import hashlib
import json
from pathlib import Path


def ensure_alias(path):
    path = Path(path)
    before = path.read_bytes()
    lines = before.decode("utf-8").splitlines(keepends=True)
    target = []
    for index, line in enumerate(lines):
        fields = line.rstrip("\r\n").split(":")
        if fields[0] == "70890":
            target.append((index, fields))
        if "Proxima Centauri" in fields[1:] and fields[0] != "70890":
            raise ValueError("Proxima Centauri is already assigned to another catalog entry")
    if len(target) != 1 or "Proxima" not in target[0][1][1:]:
        raise ValueError("Expected one HIP 70890 entry with the Proxima alias")
    index, fields = target[0]
    old_line = lines[index]
    if "Proxima Centauri" not in fields[1:]:
        ending = "\r\n" if old_line.endswith("\r\n") else "\n" if old_line.endswith("\n") else ""
        lines[index] = old_line.rstrip("\r\n") + ":Proxima Centauri" + ending
    after = "".join(lines).encode("utf-8")
    if after != before:
        # Keep the installed file's owner and mode; this runs only on a powered
        # off application in an isolated image build or maintenance overlay.
        path.write_bytes(after)
    return {
        "catalog": str(path), "hip": 70890, "alias": "Proxima Centauri",
        "changed": after != before,
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(),
        "before_line": old_line.rstrip("\r\n"),
        "after_line": lines[index].rstrip("\r\n"),
        "coordinates_or_radii_changed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = json.dumps(ensure_alias(args.catalog), indent=2) + "\n"
    if args.receipt:
        args.receipt.write_text(result)
    print(result, end="")
