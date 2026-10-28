#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shlex
import stat
import sys
from pathlib import Path

OWNER = "mac-ops/12.pi-input-gate.v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Install or undo the local Pi input gate."
    )
    parser.add_argument("action", choices=["install", "status", "uninstall"])
    parser.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).with_name("pi_agent_gate.py")
    )
    args = parser.parse_args()
    folder = args.bin_dir.expanduser().resolve()
    entry = folder / "pi"
    backup = folder / "pi.before-mac-ops-12"
    receipt = folder / "pi.mac-ops-12.json"
    saved = None
    if receipt.is_symlink():
        raise RuntimeError("Install receipt must not be a symlink.")
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if not isinstance(saved, dict) or saved.get("owner") != OWNER:
            raise RuntimeError(
                "Unrecognized install receipt; refusing to overwrite anything."
            )
        if not all(
            isinstance(saved.get(key), str)
            for key in ["original_link", "real", "sha256"]
        ):
            raise RuntimeError("Invalid install receipt.")
    if args.action == "status":
        active = (
            receipt.is_file()
            and backup.is_symlink()
            and entry.is_file()
            and not entry.is_symlink()
        )
        if active:
            active = digest(entry) == saved.get("sha256")
        print(
            json.dumps({"active": active, "entry": str(entry), "backup": str(backup)})
        )
        return
    if args.action == "uninstall":
        if saved is None:
            raise RuntimeError("No installation receipt.")
        if not backup.is_symlink() or os.readlink(backup) != saved["original_link"]:
            raise RuntimeError(
                "Original launcher backup changed; refusing to overwrite anything."
            )
        if (
            entry.is_symlink()
            or not entry.is_file()
            or digest(entry) != saved["sha256"]
        ):
            raise RuntimeError(
                "Installed launcher changed; refusing to overwrite anything."
            )
        os.replace(backup, entry)
        print(
            "Restored original Pi launcher. The inactive receipt remains at "
            + str(receipt)
        )
        return
    source = args.source.resolve(strict=True)
    source_sha = digest(source)

    def write_receipt(payload: dict) -> None:
        receipt.write_text(json.dumps(payload, indent=2) + "\n")
        receipt.chmod(0o600)

    def replace_entry_from_source() -> None:
        staged = folder / ("pi.mac-ops-12-stage-" + str(os.getpid()))
        with staged.open("xb") as stream:
            stream.write(source.read_bytes())
        staged.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        os.replace(staged, entry)

    if (
        saved
        and entry.is_file()
        and not entry.is_symlink()
        and backup.is_symlink()
        and digest(entry) == source_sha
    ):
        print(
            json.dumps(
                {
                    "already_installed": True,
                    "entry": str(entry),
                    "sha256": source_sha,
                }
            )
        )
        return

    if saved and entry.is_file() and not entry.is_symlink() and backup.is_symlink():
        replace_entry_from_source()
        saved = dict(saved)
        saved["sha256"] = source_sha
        write_receipt(saved)
        print(
            json.dumps(
                {
                    "updated": str(entry),
                    "sha256": source_sha,
                    "undo": shlex.join(["mv", str(backup), str(entry)]),
                }
            )
        )
        return

    if not entry.is_symlink() or backup.exists():
        raise RuntimeError("Expected an original Pi symlink and no existing backup.")
    original = os.readlink(entry)
    if saved and saved["original_link"] != original:
        raise RuntimeError("Existing receipt describes a different original launcher.")
    real = entry.resolve(strict=True)
    if not real.is_file() or not os.access(real, os.X_OK):
        raise RuntimeError("Original Pi target is not executable.")
    if folder.stat().st_uid != os.getuid() or real == source.resolve():
        raise RuntimeError(
            "Launcher folder must belong to this user and the original must be distinct."
        )
    staged = folder / ("pi.mac-ops-12-stage-" + str(os.getpid()))
    with staged.open("xb") as stream:
        stream.write(source.read_bytes())
    staged.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    saved = {
        "owner": OWNER,
        "original_link": original,
        "real": str(real),
        "sha256": digest(staged),
    }
    write_receipt(saved)
    os.rename(entry, backup)
    try:
        os.replace(staged, entry)
    except BaseException:
        os.replace(backup, entry)
        raise
    print(
        json.dumps(
            {
                "installed": str(entry),
                "original": original,
                "sha256": saved["sha256"],
                "undo": shlex.join(["mv", str(backup), str(entry)]),
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        sys.exit("pi gate installer: " + str(error))
