"""Create or update the ClauseCatcher Render web service via the Render REST API.

Reads settings from render.yaml, sets env vars (secrets read from THIS
process's environment at runtime, never stored or printed), deploys, waits
until live, pins CLAUSECATCHER_ALLOWED_ORIGINS to the service URL, redeploys,
then checks /api/health.

API reference (fetched 2026-09-17, payload shape re-verified against it the
same day): https://api-docs.render.com/reference
  Confirmed: `plan`, `region`, `runtime` and `envSpecificDetails` all live
  INSIDE serviceDetails (not top level); `runtime` is current, `env` is the
  deprecated spelling; `plan: free` is still a valid enum value alongside the
  newer 0.5c-512mb naming; PUT env-vars takes a bare array and replaces ALL
  vars without deploying; deployMode `deploy_only` cannot be combined with
  clearCache/commitId/imageUrl (this script never does).
  GET   /owners                                  list-owners
  GET   /services?name=&type=&ownerId=           list-services
  POST  /services                                create-service (returns service + deployId)
  PATCH /services/{id}                           update-service (does not deploy)
  PUT   /services/{id}/env-vars                  update-env-vars (replaces ALL; does not deploy)
  POST  /services/{id}/deploys                   create-deploy
  GET   /services/{id}/deploys/{deployId}        retrieve-deploy

Usage (repo root):
  python tools/deploy/render_deploy.py --dry-run     # no network, prints planned calls
  RENDER_API_KEY=... ASSEMBLYAI_API_KEY=... GEMINI_API_KEY=... python tools/deploy/render_deploy.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.render.com/v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
ORIGINS_KEY = "CLAUSECATCHER_ALLOWED_ORIGINS"
REQUIRED_SECRETS = ("ASSEMBLYAI_API_KEY", "GEMINI_API_KEY")
LIVE, FAILED = "live", {"build_failed", "update_failed", "canceled", "pre_deploy_failed", "deactivated"}
SECRET_HINTS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def is_secret(key: str) -> bool:
    return any(h in key.upper() for h in SECRET_HINTS)


def redact(obj):
    """Deep copy with env var values of secret-looking keys replaced."""
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    if isinstance(obj, dict):
        out = {k: redact(v) for k, v in obj.items()}
        if "key" in obj and "value" in obj and is_secret(str(obj["key"])):
            out["value"] = "<redacted>"
        return out
    return obj


def load_blueprint(name: str | None) -> dict:
    try:
        import yaml
    except ImportError:
        raise SystemExit("needs PyYAML: pip install pyyaml")
    services = yaml.safe_load((REPO_ROOT / "render.yaml").read_text(encoding="utf-8"))["services"]
    svc = next((s for s in services if name in (None, s["name"])), None)
    if svc is None or svc.get("type") != "web" or svc.get("runtime") != "docker":
        raise SystemExit("render.yaml: expected a docker web service")
    return svc


def env_vars(svc: dict, origin: str | None, allow_missing: bool) -> list[dict]:
    """render.yaml values as-is; `sync: false` ones from the local env (skipped if unset)."""
    out, missing = [], []
    for ev in svc.get("envVars", []):
        key = ev["key"]
        if key == ORIGINS_KEY:
            value = origin
        elif "value" in ev:
            value = str(ev["value"])
        else:
            value = os.environ.get(key) or None
        if value is None:
            if key in REQUIRED_SECRETS:
                missing.append(key)
                if allow_missing == "dry":
                    out.append({"key": key, "value": "<not set locally: a real run aborts here>"})
            continue
        out.append({"key": key, "value": value})
    if missing and not allow_missing:
        raise SystemExit(f"missing in local environment: {', '.join(missing)} (or pass --allow-missing-keys)")
    return out


class Render:
    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self.key = os.environ.get("RENDER_API_KEY")
        if not dry_run and not self.key:
            raise SystemExit("RENDER_API_KEY is not set")

    def call(self, method: str, path: str, body=None, query: dict | None = None, fake=None):
        url = API + path + ("?" + urllib.parse.urlencode(query, doseq=True) if query else "")
        print(f"{'[dry-run] ' if self.dry_run else ''}{method} {url}")
        if body is not None:
            print("  body:", json.dumps(redact(body), indent=2).replace("\n", "\n  "))
        if self.dry_run:
            return fake
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Authorization", f"Bearer {self.key}")  # never printed
        req.add_header("Accept", "application/json")
        req.add_header("Content-Type", "application/json")
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    time.sleep(2 ** attempt * 5)
                    continue
                detail = e.read().decode("utf-8", "replace")[:500]
                raise SystemExit(f"Render API {method} {path} -> HTTP {e.code}: {detail}") from None


def wait_live(api: Render, service_id: str, deploy_id: str, timeout_s: int) -> None:
    if api.dry_run:
        api.call("GET", f"/services/{service_id}/deploys/{deploy_id}")
        print("  [dry-run] poll every 15 s until status == live (fail on " + ", ".join(sorted(FAILED)) + ")")
        return
    deadline, last = time.monotonic() + timeout_s, None
    while time.monotonic() < deadline:
        status = api.call("GET", f"/services/{service_id}/deploys/{deploy_id}")["status"]
        if status != last:
            print(f"  deploy {deploy_id}: {status}")
            last = status
        if status == LIVE:
            return
        if status in FAILED:
            raise SystemExit(f"deploy {deploy_id} ended {status}; check the Logs tab in the Render dashboard")
        time.sleep(15)
    raise SystemExit(f"deploy {deploy_id} not live after {timeout_s}s")


def health(url: str, dry_run: bool) -> None:
    target = url.rstrip("/") + "/api/health"
    print(f"{'[dry-run] ' if dry_run else ''}GET {target}  (expect {{\"status\":\"ok\"}}; retries cover the ~1 min free-tier cold start)")
    if dry_run:
        return
    for _ in range(12):
        try:
            with urllib.request.urlopen(target, timeout=30) as r:
                if json.load(r).get("status") == "ok":
                    print("  health: ok")
                    return
        except Exception as e:  # noqa: BLE001
            print(f"  health not ready: {type(e).__name__}")
        time.sleep(10)
    raise SystemExit("health check failed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print planned API calls (secrets redacted); no network")
    ap.add_argument("--repo", default="https://github.com/ishal1410/clausecatcher")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--region", default="oregon", help="oregon|ohio|virginia|frankfurt|singapore (create only)")
    ap.add_argument("--service-name", default=None, help="default: the name in render.yaml")
    ap.add_argument("--owner-id", default=None, help="workspace id; required only if your key sees several")
    ap.add_argument("--allow-missing-keys", action="store_true", help="deploy without ASSEMBLYAI/GEMINI keys (app runs in simulate-only mode)")
    ap.add_argument("--timeout-s", type=int, default=1500, help="per-deploy wait (free Docker builds are slow)")
    args = ap.parse_args()

    svc = load_blueprint(args.service_name)
    name = svc["name"]
    api = Render(args.dry_run)
    mode = "dry" if args.dry_run else args.allow_missing_keys
    print("local env: " + ", ".join(f"{k}={'set' if os.environ.get(k) else 'UNSET'}" for k in ("RENDER_API_KEY", *REQUIRED_SECRETS)))
    # predicted URL guards the WebSocket origin during the first deploy; step 4 pins the real one
    envs = env_vars(svc, f"https://{name}.onrender.com", mode)

    # 1. workspace
    owners = api.call("GET", "/owners", query={"limit": 100}, fake=[{"owner": {"id": "tea-DRYRUN", "name": "you"}}])
    owner_ids = [o["owner"]["id"] for o in owners]
    if args.owner_id:
        if args.owner_id not in owner_ids:
            raise SystemExit(f"--owner-id not visible to this key (have: {owner_ids})")
        owner_id = args.owner_id
    elif len(owner_ids) == 1:
        owner_id = owner_ids[0]
    else:
        raise SystemExit(f"key sees {len(owner_ids)} workspaces; pass --owner-id one of {owner_ids}")

    # 2. existing service?
    found = api.call("GET", "/services", query={"name": name, "type": "web_service", "ownerId": owner_id, "limit": 20}, fake=[])
    existing = next((x["service"] for x in found if x["service"]["name"] == name), None)

    service_details = {
        "plan": svc.get("plan", "free"),
        "healthCheckPath": svc.get("healthCheckPath", "/api/health"),
        "envSpecificDetails": {
            "dockerfilePath": svc.get("dockerfilePath", "./Dockerfile"),
            "dockerContext": svc.get("dockerContext", "."),
        },
    }

    # 3. create (deploys automatically) or update + deploy
    if existing is None:
        print(f"service '{name}' not found in {owner_id}: creating")
        body = {
            "type": "web_service",
            "name": name,
            "ownerId": owner_id,
            "repo": args.repo,
            "branch": args.branch,
            "autoDeploy": "yes",
            "envVars": envs,
            "serviceDetails": {**service_details, "runtime": "docker", "region": args.region},
        }
        created = api.call(
            "POST", "/services", body,
            fake={"service": {"id": "srv-DRYRUN", "serviceDetails": {"url": f"https://{name}.onrender.com"}}, "deployId": "dep-DRYRUN1"},
        )
        service, deploy_id = created["service"], created["deployId"]
    else:
        service = existing
        print(f"service '{name}' exists ({service['id']}): updating")
        api.call("PATCH", f"/services/{service['id']}", {"repo": args.repo, "branch": args.branch, "autoDeploy": "yes", "serviceDetails": service_details})
        # keep a previously pinned origin so this intermediate deploy doesn't open the WS to any origin
        url0 = service.get("serviceDetails", {}).get("url") or f"https://{name}.onrender.com"
        api.call("PUT", f"/services/{service['id']}/env-vars", env_vars(svc, url0, mode))
        deploy_id = api.call("POST", f"/services/{service['id']}/deploys", {"clearCache": "do_not_clear"}, fake={"id": "dep-DRYRUN1"})["id"]

    sid = service["id"]
    wait_live(api, sid, deploy_id, args.timeout_s)

    # 4. pin allowed origin to the real URL, redeploy
    # fall back to the predicted URL rather than KeyError-ing away a build that
    # just took ten minutes on the free tier
    url = service.get("serviceDetails", {}).get("url") or f"https://{name}.onrender.com"
    print(f"service URL: {url}")
    api.call("PUT", f"/services/{sid}/env-vars", env_vars(svc, url, mode))
    # env-only change: restart the already-built image instead of a second slow free-tier build
    deploy2 = api.call("POST", f"/services/{sid}/deploys", {"deployMode": "deploy_only"}, fake={"id": "dep-DRYRUN2"})["id"]
    wait_live(api, sid, deploy2, args.timeout_s)

    # 5. health
    health(url, args.dry_run)
    print(f"DRY RUN complete, nothing was sent. Would deploy: {url}" if args.dry_run else f"DEPLOYED: {url}")
    return 0


def _selftest() -> None:
    """ponytail check: redaction + env assembly, no network."""
    body = [{"key": "GEMINI_API_KEY", "value": "sk-live"}, {"key": "CLAUSECATCHER_BUDGET_USD", "value": "3"}]
    assert redact(body) == [{"key": "GEMINI_API_KEY", "value": "<redacted>"}, {"key": "CLAUSECATCHER_BUDGET_USD", "value": "3"}]
    assert "sk-live" not in json.dumps(redact({"envVars": body}))
    svc = {"envVars": [{"key": "ASSEMBLYAI_API_KEY", "sync": False}, {"key": ORIGINS_KEY, "sync": False}, {"key": "X", "value": 2}]}
    os.environ.pop("ASSEMBLYAI_API_KEY", None)
    assert env_vars(svc, "https://a.onrender.com", True) == [{"key": ORIGINS_KEY, "value": "https://a.onrender.com"}, {"key": "X", "value": "2"}]
    try:
        env_vars(svc, None, False)
        raise AssertionError("missing key not caught")
    except SystemExit:
        pass
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        _selftest()
        sys.exit(0)
    sys.exit(main())
