#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "sources.json"
OUTPUT_FILE = ROOT / "manifest.json"
REQUIRED_PLUGIN_FIELDS = {"guid", "name", "versions"}
REQUIRED_VERSION_FIELDS = {"version", "targetAbi", "sourceUrl", "checksum"}


def fetch_json(url: str):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ODOS3D-Jellyfin-Manifest-Aggregator/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def validate_plugin(plugin: dict, source: str) -> None:
    missing = REQUIRED_PLUGIN_FIELDS - plugin.keys()
    if missing:
        raise ValueError(f"{source}: plugin missing fields: {sorted(missing)}")
    if not isinstance(plugin["versions"], list) or not plugin["versions"]:
        raise ValueError(f"{source}: {plugin.get('name', 'plugin')} has no versions")
    for version in plugin["versions"]:
        missing_version = REQUIRED_VERSION_FIELDS - version.keys()
        if missing_version:
            raise ValueError(
                f"{source}: {plugin['name']} version {version.get('version', '?')} "
                f"missing fields: {sorted(missing_version)}"
            )


def main() -> int:
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources.json must contain at least one manifest URL")

    plugins: list[dict] = []
    seen_guids: dict[str, str] = {}

    for source in sources:
        payload = fetch_json(source)
        if not isinstance(payload, list):
            raise ValueError(f"{source}: manifest root must be an array")
        for plugin in payload:
            if not isinstance(plugin, dict):
                raise ValueError(f"{source}: invalid plugin entry")
            validate_plugin(plugin, source)
            guid = str(plugin["guid"]).lower()
            if guid in seen_guids:
                raise ValueError(
                    f"duplicate plugin GUID {guid}: {seen_guids[guid]} and {source}"
                )
            seen_guids[guid] = source
            plugins.append(plugin)

    plugins.sort(key=lambda item: str(item.get("name", "")).casefold())
    rendered = json.dumps(plugins, ensure_ascii=False, indent=2) + "\n"
    OUTPUT_FILE.write_text(rendered, encoding="utf-8")
    print(f"Wrote {len(plugins)} plugins from {len(sources)} sources to {OUTPUT_FILE.name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        raise
