#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("JELLYFIN_URL", "http://127.0.0.1:8096").rstrip("/")
CLIENT_HEADER = 'MediaBrowser Client="ODOS3D%20Catalog%20E2E", DeviceId="odos3d-catalog-e2e", Device="GitHub%20Actions", Version="1.0"'
ADMIN_NAME = "catalog-admin"
ADMIN_PASSWORD = "catalog-admin-password"


def call(method: str, path: str, body=None, token: str | None = None, expected=(200, 204), raw=False):
    data = None
    headers = {"Accept": "application/json", "Authorization": CLIENT_HEADER + (f", Token={token}" if token else "")}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            status = response.status
            content_type = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        status = exc.code
        content_type = exc.headers.get("content-type", "")
    if status not in expected:
        raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {payload[:1000]!r}")
    if raw:
        return status, payload, content_type
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def pick(obj: dict, name: str):
    return obj.get(name) if name in obj else obj.get(name[0].lower() + name[1:])


def wait_for_server() -> None:
    deadline = time.time() + 150
    last_error = None
    while time.time() < deadline:
        try:
            status, payload, _ = call("GET", "/System/Info/Public", expected=(200,), raw=True)
            if status == 200 and payload:
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"Jellyfin did not start: {last_error}")


def authenticate(username: str, password: str) -> str:
    result = call("POST", "/Users/AuthenticateByName", {"Username": username, "Pw": password}, expected=(200,))
    token = pick(result, "AccessToken")
    if not token:
        raise AssertionError(f"No access token for {username}: {result}")
    return token


def main() -> None:
    wait_for_server()

    initial_user = call("GET", "/Startup/User", expected=(200,))
    if not pick(initial_user, "Name"):
        raise AssertionError(initial_user)
    call("POST", "/Startup/Configuration", {
        "UICulture": "es-ES",
        "MetadataCountryCode": "ES",
        "PreferredMetadataLanguage": "es",
    }, expected=(204,))
    call("POST", "/Startup/User", {"Name": ADMIN_NAME, "Password": ADMIN_PASSWORD}, expected=(204,))
    call("POST", "/Startup/RemoteAccess", {"EnableRemoteAccess": False, "EnableAutomaticPortMapping": False}, expected=(204,))
    call("POST", "/Startup/Complete", expected=(204,))

    token = authenticate(ADMIN_NAME, ADMIN_PASSWORD)
    me = call("GET", "/Users/Me", token=token, expected=(200,))
    user_id = pick(me, "Id")
    if not user_id:
        raise AssertionError(me)

    _, index_bytes, index_type = call("GET", "/web/index.html", token=token, expected=(200,), raw=True)
    index = index_bytes.decode("utf-8", errors="replace")
    if "data-jellyfin-community-bootstrap" not in index:
        raise AssertionError("Community bootstrap missing from combined Jellyfin Web index")
    if "data-jellypremiere-client" not in index:
        raise AssertionError("JellyPremiere bootstrap missing when Community and JellyPremiere are installed together")
    if "text/html" not in index_type.lower():
        raise AssertionError(index_type)

    config = call("GET", "/web/config.json", token=token, expected=(200,))
    menu_links = pick(config, "menuLinks") or []
    if not any(pick(link, "name") == "Foro" for link in menu_links):
        raise AssertionError(f"Forum menu link missing: {menu_links}")

    channels = call("GET", "/Channels?" + urllib.parse.urlencode({"userId": user_id}), token=token, expected=(200,))
    names = {pick(item, "Name") for item in (pick(channels, "Items") or [])}
    if "Foro" not in names:
        raise AssertionError(f"Native Community channel missing: {sorted(str(name) for name in names)}")
    if "Estrenos" not in names:
        raise AssertionError(f"Native JellyPremiere channel missing: {sorted(str(name) for name in names)}")
    if "Viendo en TV" in names:
        raise AssertionError("JellyLiveNow must stay hidden when there is no active Live TV session")

    categories = call("GET", "/Community/api/v1/categories", token=token, expected=(200,))
    if not isinstance(categories, list) or len(categories) < 3:
        raise AssertionError(f"Community API did not initialize correctly: {categories}")

    premiere = call("GET", "/JellyPremiere/Active", token=token, expected=(200,))
    if premiere != []:
        raise AssertionError(f"Fresh JellyPremiere install should have no announcements: {premiere}")

    live_now = call("GET", "/JellyLiveNow/Status", token=token, expected=(200,))
    if bool(pick(live_now, "IsActive")):
        raise AssertionError(f"Fresh JellyLiveNow install should be inactive: {live_now}")

    evidence = {
        "status": "passed",
        "web": {"community": True, "jellyPremiere": True, "forumMenu": True},
        "nativeChannels": sorted(str(name) for name in names if name),
        "communityCategories": len(categories),
        "premiereActiveAnnouncements": len(premiere),
        "liveNowActive": bool(pick(live_now, "IsActive")),
    }
    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/combined-runtime-e2e.json", "w", encoding="utf-8") as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
