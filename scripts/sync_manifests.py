#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "sources.json"
OUTPUT_FILE = ROOT / "manifest.json"
TARGET_ABI = "10.10.7.0"
MAX_PACKAGE_BYTES = 50 * 1024 * 1024
MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,3}$")


def fetch_bytes(url: str, *, max_bytes: int | None = None, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ODOS3D-Jellyfin-Repository/1.1"})
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status} for {url}")
                if max_bytes is None:
                    return response.read()
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise ValueError(f"Package exceeds {max_bytes} bytes: {url}")
                return payload
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def load_json_url(url: str):
    try:
        return json.loads(fetch_bytes(url).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON from {url}: {exc}") from exc


def validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {"raw.githubusercontent.com", "github.com"}:
        raise ValueError(f"Unsupported source URL: {url}")
    if "/odoslf/" not in parsed.path:
        raise ValueError(f"Source is outside the odoslf repositories: {url}")


def version_key(number: str) -> tuple[int, int, int, int]:
    if not VERSION_RE.fullmatch(number):
        raise ValueError(f"Invalid numeric plugin version: {number!r}")
    parts = [int(part) for part in number.split(".")]
    if len(parts) > 4:
        raise ValueError(f"Plugin version has too many components: {number!r}")
    return tuple((parts + [0] * (4 - len(parts)))[:4])  # type: ignore[return-value]


def validate_release(plugin_name: str, version: dict) -> None:
    number = version.get("version")
    if not isinstance(number, str) or not number.strip():
        raise ValueError(f"{plugin_name}: version is missing")
    version_key(number)

    if version.get("targetAbi") != TARGET_ABI:
        raise ValueError(f"{plugin_name} {number}: targetAbi must be {TARGET_ABI}")

    source_url = version.get("sourceUrl")
    if not isinstance(source_url, str) or not source_url.startswith("https://github.com/odoslf/"):
        raise ValueError(f"{plugin_name} {number}: invalid release sourceUrl")

    checksum = version.get("checksum")
    if not isinstance(checksum, str) or not MD5_RE.fullmatch(checksum):
        raise ValueError(f"{plugin_name} {number}: checksum must be a final 32-character MD5")

    package = fetch_bytes(source_url, max_bytes=MAX_PACKAGE_BYTES)
    if len(package) < 4 or package[:2] != b"PK":
        raise ValueError(f"{plugin_name} {number}: release asset is not a ZIP package")

    actual = hashlib.md5(package).hexdigest()
    if actual.lower() != checksum.lower():
        raise ValueError(
            f"{plugin_name} {number}: checksum mismatch; manifest={checksum.lower()} release={actual.lower()}"
        )


def normalize_plugin(plugin: dict, source_url: str) -> dict:
    required = ("guid", "name", "description", "overview", "owner", "category", "versions")
    missing = [key for key in required if key not in plugin]
    if missing:
        raise ValueError(f"{source_url}: plugin missing fields {missing}")
    if plugin.get("owner") != "odoslf":
        raise ValueError(f"{source_url}: unexpected owner {plugin.get('owner')!r}")
    versions = plugin.get("versions")
    if not isinstance(versions, list) or not versions:
        raise ValueError(f"{source_url}: plugin has no versions")

    seen_versions: set[str] = set()
    candidates: list[dict] = []
    for version in versions:
        if not isinstance(version, dict):
            raise ValueError(f"{source_url}: invalid version entry")
        number = version.get("version")
        if not isinstance(number, str):
            raise ValueError(f"{source_url}: version is missing")
        version_key(number)
        if number in seen_versions:
            raise ValueError(f"{source_url}: duplicate version {number}")
        seen_versions.add(number)
        candidates.append(version)

    # The unified repository intentionally exposes only the newest release from
    # each source. Historical packages are not needed for fresh installs and a
    # deleted/broken legacy asset must not prevent a valid current release from
    # being published. The newest package is still downloaded and cryptographically
    # matched against the manifest MD5 before it is accepted.
    latest = max(candidates, key=lambda item: version_key(item["version"]))
    validate_release(plugin["name"], latest)

    normalized = dict(plugin)
    normalized["versions"] = [latest]
    return normalized


def main() -> None:
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources.json must contain a non-empty JSON array")

    plugins: list[dict] = []
    seen_guids: set[str] = set()
    seen_names: set[str] = set()

    for source_url in sources:
        if not isinstance(source_url, str):
            raise ValueError("Every source must be a URL string")
        validate_source_url(source_url)
        source = load_json_url(source_url)
        if not isinstance(source, list) or not source:
            raise ValueError(f"{source_url}: manifest must contain at least one plugin")

        for plugin in source:
            if not isinstance(plugin, dict):
                raise ValueError(f"{source_url}: invalid plugin entry")
            normalized = normalize_plugin(plugin, source_url)
            guid = str(normalized["guid"]).lower()
            name = str(normalized["name"]).casefold()
            if guid in seen_guids:
                raise ValueError(f"Duplicate plugin GUID {guid}")
            if name in seen_names:
                raise ValueError(f"Duplicate plugin name {normalized['name']}")
            seen_guids.add(guid)
            seen_names.add(name)
            plugins.append(normalized)

    plugins.sort(key=lambda item: item["name"].casefold())
    payload = json.dumps(plugins, ensure_ascii=False, indent=2) + "\n"
    temporary = OUTPUT_FILE.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(OUTPUT_FILE)
    print(f"Validated {len(plugins)} latest plugin releases for ABI {TARGET_ABI}.")


if __name__ == "__main__":
    main()
