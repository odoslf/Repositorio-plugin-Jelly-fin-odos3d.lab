#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
RUNTIME = ROOT / "runtime"
PLUGINS = RUNTIME / "config" / "plugins"
ARTIFACTS = ROOT / "artifacts"
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ODOS3D-Jellyfin-Combined-E2E/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        return response.read()


def safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if not members:
        raise ValueError("Plugin ZIP is empty")
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe ZIP member: {member.filename}")
    return members


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError(f"Expected exactly 3 plugins in unified manifest, got {len(data) if isinstance(data, list) else 'invalid'}")

    shutil.rmtree(RUNTIME, ignore_errors=True)
    shutil.rmtree(ARTIFACTS, ignore_errors=True)
    PLUGINS.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "cache").mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    evidence: list[dict[str, object]] = []
    for plugin in data:
        versions = plugin.get("versions") or []
        if len(versions) != 1:
            raise ValueError(f"{plugin.get('name')}: unified catalog must expose exactly one latest release")
        version = versions[0]
        payload = fetch(version["sourceUrl"])
        actual_md5 = hashlib.md5(payload).hexdigest()
        expected_md5 = str(version["checksum"]).lower()
        if actual_md5 != expected_md5:
            raise ValueError(f"{plugin['name']}: release changed after catalog validation")

        folder_name = SAFE_NAME.sub("-", f"{plugin['name']}_{version['version']}").strip("-")
        destination = PLUGINS / folder_name
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = safe_members(archive)
            archive.extractall(destination, members=members)

        dlls = sorted(path.name for path in destination.rglob("*.dll"))
        if not dlls:
            raise ValueError(f"{plugin['name']}: package contains no plugin DLL")
        evidence.append({
            "name": plugin["name"],
            "version": version["version"],
            "targetAbi": version["targetAbi"],
            "checksum": expected_md5,
            "packageBytes": len(payload),
            "dlls": dlls,
        })

    (ARTIFACTS / "combined-packages.json").write_text(
        json.dumps({"status": "prepared", "plugins": evidence}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
