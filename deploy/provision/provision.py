#!/usr/bin/env python3
"""Provision the BoxTech demo tenant against a freshly installed platform.

Everything the evaluation asks for is created here over the REST API, so a clean
`docker compose up` reproduces the exact same environment - tenant, customer,
customer user, device profile with the overspeed and low-fuel alarm rules, the
device with a fixed access token, and the vehicle tracking dashboard.

The script is idempotent: each entity is looked up before it is created, so
re-running against an already-provisioned instance is a no-op.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

import fleet_dashboards

BASE_URL = os.environ.get("TB_BASE_URL", "http://boxtech-platform:8080").rstrip("/")

SYSADMIN_EMAIL = os.environ.get("TB_SYSADMIN_EMAIL", "sysadmin@thingsboard.org")
SYSADMIN_PASSWORD = os.environ.get("TB_SYSADMIN_PASSWORD", "sysadmin")

TENANT_TITLE = os.environ.get("BOXTECH_TENANT_TITLE", "BoxTech Logistics")
TENANT_ADMIN_EMAIL = os.environ.get("BOXTECH_TENANT_EMAIL", "tenant@boxtech.io")
TENANT_ADMIN_PASSWORD = os.environ.get("BOXTECH_TENANT_PASSWORD", "BoxTech@2026")

CUSTOMER_TITLE = os.environ.get("BOXTECH_CUSTOMER_TITLE", "Demo Logistics Company")
CUSTOMER_USER_EMAIL = os.environ.get("BOXTECH_CUSTOMER_EMAIL", "demo.user@demologistics.com")
CUSTOMER_USER_PASSWORD = os.environ.get("BOXTECH_CUSTOMER_PASSWORD", "Password123!")

DEVICE_NAME = os.environ.get("BOXTECH_DEVICE_NAME", "Demo Vehicle GPS Tracker")
DEVICE_TOKEN = os.environ.get("BOXTECH_DEVICE_TOKEN", "DEMO_VEHICLE_TRACKER_TOKEN")
DEVICE_TOKEN_2 = os.environ.get("BOXTECH_DEVICE_TOKEN_2", "BT_TRK_002_TOKEN")
DEVICE_TOKEN_3 = os.environ.get("BOXTECH_DEVICE_TOKEN_3", "BT_TRK_003_TOKEN")
DEVICE_PROFILE_NAME = os.environ.get("BOXTECH_DEVICE_PROFILE", "BoxTech Vehicle Tracker")

DASHBOARD_TITLE = "Vehicle Tracking Dashboard"
DASHBOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "dashboard_vehicle_tracking.json")

OVERSPEED_LIMIT = float(os.environ.get("BOXTECH_SPEED_LIMIT", "80"))
LOW_FUEL_LIMIT = float(os.environ.get("BOXTECH_FUEL_LIMIT", "20"))

# The device is marked inactive this long after its last telemetry, which drives
# the online/offline indicator and the "Vehicle Offline" alarm.
INACTIVITY_TIMEOUT_MS = int(os.environ.get("BOXTECH_INACTIVITY_TIMEOUT_MS", "60000"))


def log(msg: str) -> None:
    print(f"[provision] {msg}", flush=True)


class Api:
    """Thin REST wrapper that carries one user's JWT."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()

    def login(self, username: str, password: str) -> None:
        r = self.session.post(
            f"{self.base_url}/api/auth/login",
            json={"username": username, "password": password},
            timeout=30,
        )
        r.raise_for_status()
        self.set_token(r.json()["token"])

    def set_token(self, token: str) -> None:
        self.session.headers["X-Authorization"] = f"Bearer {token}"

    def request(self, method: str, path: str, **kw) -> requests.Response:
        r = self.session.request(method, f"{self.base_url}{path}", timeout=60, **kw)
        if not r.ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:800]}")
        return r

    def get(self, path: str, **kw) -> Any:
        return self.request("GET", path, **kw).json()

    def post(self, path: str, **kw) -> Any:
        r = self.request("POST", path, **kw)
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None

    def get_text(self, path: str) -> str:
        return self.request("GET", path).text

    def find_page(self, path: str, text_search: str, match: str = "name") -> dict | None:
        """Page-search endpoints return {data: [...]}; match one entity exactly."""
        data = self.get(
            path,
            params={"pageSize": 200, "page": 0, "textSearch": text_search,
                    "sortProperty": "createdTime", "sortOrder": "ASC"},
        )
        for item in data.get("data", []):
            if item.get(match) == text_search:
                return item
        return None


def wait_for_platform(base_url: str, timeout_s: int = 900) -> None:
    log(f"waiting for the platform at {base_url}")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/login", timeout=10)
            if r.status_code == 200:
                log("platform is up")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise SystemExit(f"platform did not come up within {timeout_s}s")


def activate_user(api: Api, user_id: str, password: str) -> None:
    """Set a password without going through activation e-mail."""
    link = api.get_text(f"/api/user/{user_id}/activationLink")
    token = parse_qs(urlparse(link.strip()).query).get("activateToken", [None])[0]
    if not token:
        raise RuntimeError(f"could not read activateToken from activation link: {link!r}")
    r = requests.post(
        f"{api.base_url}/api/noauth/activate",
        json={"activateToken": token, "password": password},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"activate failed -> {r.status_code}: {r.text[:400]}")


# ---------------------------------------------------------------------------
# Alarm rules
# ---------------------------------------------------------------------------

def numeric_filter(key: str, operation: str, value: float) -> dict:
    return {
        "key": {"type": "TIME_SERIES", "key": key},
        "valueType": "NUMERIC",
        "value": None,
        "predicate": {
            "type": "NUMERIC",
            "operation": operation,
            "value": {"defaultValue": value, "userValue": None, "dynamicValue": None},
        },
    }


def boolean_filter(key: str, value: bool, key_type: str = "ATTRIBUTE") -> dict:
    return {
        "key": {"type": key_type, "key": key},
        "valueType": "BOOLEAN",
        "value": None,
        "predicate": {
            "type": "BOOLEAN",
            "operation": "EQUAL",
            "value": {"defaultValue": value, "userValue": None, "dynamicValue": None},
        },
    }


def alarm_rule(filters: list[dict], details: str) -> dict:
    return {
        "condition": {"condition": filters, "spec": {"type": "SIMPLE"}},
        "schedule": None,
        "alarmDetails": details,
        "dashboardId": None,
    }


def profile_alarms() -> list[dict]:
    return [
        {
            "id": "boxtech-overspeed",
            "alarmType": "Overspeed Alert",
            "createRules": {
                "CRITICAL": alarm_rule(
                    [numeric_filter("speed", "GREATER", OVERSPEED_LIMIT)],
                    f"Vehicle speed exceeded the {OVERSPEED_LIMIT:.0f} km/h limit.",
                )
            },
            "clearRule": alarm_rule(
                [numeric_filter("speed", "LESS_OR_EQUAL", OVERSPEED_LIMIT)],
                f"Vehicle speed is back within the {OVERSPEED_LIMIT:.0f} km/h limit.",
            ),
            "propagate": False,
            "propagateToOwner": False,
            "propagateToTenant": False,
            "propagateRelationTypes": None,
        },
        {
            "id": "boxtech-low-fuel",
            "alarmType": "Low Fuel Alert",
            "createRules": {
                "WARNING": alarm_rule(
                    [numeric_filter("fuel", "LESS", LOW_FUEL_LIMIT)],
                    f"Fuel level dropped below {LOW_FUEL_LIMIT:.0f}%.",
                )
            },
            "clearRule": alarm_rule(
                [numeric_filter("fuel", "GREATER_OR_EQUAL", LOW_FUEL_LIMIT)],
                f"Fuel level recovered above {LOW_FUEL_LIMIT:.0f}%.",
            ),
            "propagate": False,
            "propagateToOwner": False,
            "propagateToTenant": False,
            "propagateRelationTypes": None,
        },
        {
            "id": "boxtech-offline",
            "alarmType": "Vehicle Offline",
            "createRules": {
                "MAJOR": alarm_rule(
                    [boolean_filter("active", False)],
                    "No telemetry received from the tracker; the vehicle is offline.",
                )
            },
            "clearRule": alarm_rule(
                [boolean_filter("active", True)],
                "Tracker is reporting again; the vehicle is back online.",
            ),
            "propagate": False,
            "propagateToOwner": False,
            "propagateToTenant": False,
            "propagateRelationTypes": None,
        },
    ]


def device_profile_body() -> dict:
    return {
        "name": DEVICE_PROFILE_NAME,
        "description": "Vehicle tracker profile with BoxTech fleet alarm rules.",
        "type": "DEFAULT",
        "transportType": "DEFAULT",
        "provisionType": "DISABLED",
        "provisionDeviceKey": None,
        "default": False,
        "profileData": {
            "configuration": {"type": "DEFAULT"},
            "transportConfiguration": {"type": "DEFAULT"},
            "provisionConfiguration": {"type": "DISABLED", "provisionDeviceSecret": None},
            "alarms": profile_alarms(),
        },
    }


# ---------------------------------------------------------------------------
# Provisioning steps
# ---------------------------------------------------------------------------

def ensure_tenant(sysadmin: Api) -> dict:
    tenant = sysadmin.find_page("/api/tenants", TENANT_TITLE, match="title")
    if tenant:
        log(f"tenant '{TENANT_TITLE}' already exists")
        return tenant
    tenant = sysadmin.post("/api/tenant", json={"title": TENANT_TITLE, "country": "Pakistan",
                                                "city": "Karachi", "email": TENANT_ADMIN_EMAIL})
    log(f"created tenant '{TENANT_TITLE}'")
    return tenant


def ensure_tenant_admin(sysadmin: Api, tenant: dict) -> None:
    tenant_id = tenant["id"]["id"]
    users = sysadmin.get(f"/api/tenant/{tenant_id}/users",
                         params={"pageSize": 200, "page": 0})
    for u in users.get("data", []):
        if u.get("email") == TENANT_ADMIN_EMAIL:
            log(f"tenant admin '{TENANT_ADMIN_EMAIL}' already exists")
            return
    user = sysadmin.post(
        "/api/user",
        params={"sendActivationMail": "false"},
        json={
            "email": TENANT_ADMIN_EMAIL,
            "authority": "TENANT_ADMIN",
            "tenantId": tenant["id"],
            "firstName": "BoxTech",
            "lastName": "Administrator",
        },
    )
    activate_user(sysadmin, user["id"]["id"], TENANT_ADMIN_PASSWORD)
    log(f"created tenant admin '{TENANT_ADMIN_EMAIL}'")


def ensure_device_profile(tb: Api) -> dict:
    existing = tb.find_page("/api/deviceProfiles", DEVICE_PROFILE_NAME)
    body = device_profile_body()
    if existing:
        # Keep the alarm rules in sync with this script on re-runs.
        body["id"] = existing["id"]
        body["createdTime"] = existing.get("createdTime")
        body["tenantId"] = existing.get("tenantId")
        body["default"] = existing.get("default", False)
        profile = tb.post("/api/deviceProfile", json=body)
        log(f"updated device profile '{DEVICE_PROFILE_NAME}'")
    else:
        profile = tb.post("/api/deviceProfile", json=body)
        log(f"created device profile '{DEVICE_PROFILE_NAME}' with "
            f"{len(body['profileData']['alarms'])} alarm rules")
    return profile


def ensure_customer(tb: Api) -> dict:
    customer = tb.find_page("/api/customers", CUSTOMER_TITLE, match="title")
    if customer:
        log(f"customer '{CUSTOMER_TITLE}' already exists")
        return customer
    customer = tb.post(
        "/api/customer",
        json={
            "title": CUSTOMER_TITLE,
            "country": "Pakistan",
            "city": "Karachi",
            "address": "Shahrah-e-Faisal",
            "email": CUSTOMER_USER_EMAIL,
        },
    )
    log(f"created customer '{CUSTOMER_TITLE}'")
    return customer


def ensure_customer_user(tb: Api, customer: dict) -> dict:
    customer_id = customer["id"]["id"]
    users = tb.get(f"/api/customer/{customer_id}/users", params={"pageSize": 200, "page": 0})
    for u in users.get("data", []):
        if u.get("email") == CUSTOMER_USER_EMAIL:
            log(f"customer user '{CUSTOMER_USER_EMAIL}' already exists")
            return u
    user = tb.post(
        "/api/user",
        params={"sendActivationMail": "false"},
        json={
            "email": CUSTOMER_USER_EMAIL,
            "authority": "CUSTOMER_USER",
            "customerId": customer["id"],
            "firstName": "Demo",
            "lastName": "Manager",
        },
    )
    activate_user(tb, user["id"]["id"], CUSTOMER_USER_PASSWORD)
    log(f"created customer user '{CUSTOMER_USER_EMAIL}'")
    return user


def ensure_device(tb: Api, profile: dict, customer: dict,
                  name: str | None = None, token: str | None = None,
                  label: str | None = None) -> dict:
    # Defaults keep the original single-device behaviour; the fleet passes
    # explicit names so the extra vehicles are additive.
    name = name or DEVICE_NAME
    token = token or DEVICE_TOKEN
    label = label or "Karachi fleet - demo unit"
    try:
        device = tb.get("/api/tenant/device", params={"deviceName": name})
        log(f"device '{name}' already exists")
    except RuntimeError:
        payload = {
            "device": {
                "name": name,
                "label": label,
                "deviceProfileId": profile["id"],
                "additionalInfo": {"description": "Simulated GV30 GPS tracker."},
            },
            "credentials": {
                "credentialsType": "ACCESS_TOKEN",
                "credentialsId": token,
            },
        }
        device = tb.post("/api/device-with-credentials", json=payload)
        log(f"created device '{name}' with access token '{token}'")

    assigned = (device.get("customerId") or {}).get("id")
    if assigned != customer["id"]["id"]:
        device = tb.post(f"/api/customer/{customer['id']['id']}/device/{device['id']['id']}")
        log(f"assigned '{name}' to customer '{CUSTOMER_TITLE}'")

    tb.post(
        f"/api/plugins/telemetry/DEVICE/{device['id']['id']}/attributes/SERVER_SCOPE",
        json={"inactivityTimeout": INACTIVITY_TIMEOUT_MS},
    )
    return device


def ensure_dashboard(tb: Api, device: dict, customer: dict) -> dict:
    with open(DASHBOARD_FILE, encoding="utf-8") as f:
        raw = f.read()
    raw = raw.replace("00000000-0000-0000-0000-000000000000", device["id"]["id"])
    body = json.loads(raw)

    existing = tb.find_page("/api/tenant/dashboards", DASHBOARD_TITLE, match="title")
    if existing:
        body["id"] = existing["id"]
        body["createdTime"] = existing.get("createdTime")
        body["tenantId"] = existing.get("tenantId")
        dashboard = tb.post("/api/dashboard", json=body)
        log(f"updated dashboard '{DASHBOARD_TITLE}'")
    else:
        dashboard = tb.post("/api/dashboard", json=body)
        log(f"created dashboard '{DASHBOARD_TITLE}' "
            f"({len(body['configuration']['widgets'])} widgets)")

    dashboard_id = dashboard["id"]["id"]
    assigned = {c["id"] for c in (dashboard.get("assignedCustomers") or [])
                if isinstance(c, dict) and "id" in c}
    if customer["id"]["id"] not in {a.get("id") if isinstance(a, dict) else a for a in assigned}:
        tb.post(f"/api/customer/{customer['id']['id']}/dashboard/{dashboard_id}")
        log(f"assigned dashboard to customer '{CUSTOMER_TITLE}'")
    return dashboard


def clear_user_default_dashboard(tb: Api, user: dict) -> None:
    """Make sure the customer user has no user-level default dashboard.

    AuthService.defaultUrl() picks 'home' first and then overrides it when the
    user carries additionalInfo.defaultDashboardId:

        result = this.router.parseUrl('home');
        if (this.userHasDefaultDashboard(authState)) {
          result = this.router.parseUrl(`dashboards/${dashboardId}`);
        }

    So a user-level default is shown *instead of* /home at login. The landing
    page for this customer is the Fleet Command Center, which is a customer-level
    home dashboard, and /home is what resolves it. Leaving a user-level default
    pointing at the Vehicle Tracking Dashboard made that dashboard appear first
    and the Command Center only after navigating to /home.

    Clearing rather than simply not setting it matters: the value persists in the
    database from earlier provisioning runs, so it has to be actively removed.
    """
    info = dict(user.get("additionalInfo") or {})
    if "defaultDashboardId" not in info and "defaultDashboardFullscreen" not in info:
        return
    info.pop("defaultDashboardId", None)
    info.pop("defaultDashboardFullscreen", None)
    body = dict(user)
    body["additionalInfo"] = info
    tb.post("/api/user", params={"sendActivationMail": "false"}, json=body)
    log("cleared the user-level default dashboard so login lands on /home")



# --------------------------------------------------------------------------
# Fleet Command Center
# --------------------------------------------------------------------------

def ensure_fleet(tb: Api, profile: dict, customer: dict) -> list:
    """The three demo vehicles.

    The first keeps its original name because the existing dashboard, report and
    screenshots all refer to it; the fleet identity is carried on the label
    instead, which is what the fleet views display. The other two are additive -
    nothing about the original device changes except that label.
    """
    fleet = [ensure_device(tb, profile, customer, label="BT-TRK-001")]
    for name, token in [("BT-TRK-002", DEVICE_TOKEN_2), ("BT-TRK-003", DEVICE_TOKEN_3)]:
        fleet.append(ensure_device(tb, profile, customer, name, token, name))
    log(f"fleet: {len(fleet)} vehicles, inactivity timeout "
        f"{INACTIVITY_TIMEOUT_MS // 1000}s (drives online/offline)")
    return fleet


def ensure_fleet_overview(tb: Api, customer: dict) -> dict:
    """Build and upload the Command Center, idempotently."""
    title = fleet_dashboards.FLEET_DASHBOARD_TITLE
    catalogue = fleet_dashboards.widget_catalogue(tb)
    page = tb.get("/api/tenant/dashboards?pageSize=200&page=0")
    existing = next((d for d in page["data"] if d["title"] == title), None)

    body = fleet_dashboards.build_fleet_overview(catalogue)
    if existing:
        body["id"] = existing["id"]
        dashboard = tb.post("/api/dashboard", json=body)
        log(f"updated dashboard: {title}")
    else:
        dashboard = tb.post("/api/dashboard", json=body)
        log(f"created dashboard: {title}")

    did = dashboard["id"]["id"]
    assigned = dashboard.get("assignedCustomers") or []
    if not any(a.get("customerId", {}).get("id") == customer["id"]["id"] for a in assigned):
        dashboard = tb.post(f"/api/customer/{customer['id']['id']}/dashboard/{did}")
        log(f"assigned {title} to '{CUSTOMER_TITLE}'")
    return dashboard


def set_home_dashboard(tb: Api, customer: dict, dashboard: dict) -> None:
    """Replace the stock ThingsBoard home page for this customer.

    Without this the customer's Home is ThingsBoard's own page, which carries a
    Documentation card linking to thingsboard.io - the single most obvious tell
    that this is a rebranded install. This is also what makes the Command Center
    menu entry, which points at /home, resolve to the fleet dashboard.
    """
    full = tb.get(f"/api/customer/{customer['id']['id']}")
    info = full.get("additionalInfo") or {}
    if info.get("homeDashboardId") == dashboard["id"]["id"]:
        log("home dashboard already set")
        return
    info["homeDashboardId"] = dashboard["id"]["id"]
    info["homeDashboardHideToolbar"] = True
    full["additionalInfo"] = info
    tb.post("/api/customer", json=full)
    log(f"customer home page is now {fleet_dashboards.FLEET_DASHBOARD_TITLE}")


def main() -> int:
    wait_for_platform(BASE_URL)

    sysadmin = Api(BASE_URL)
    sysadmin.login(SYSADMIN_EMAIL, SYSADMIN_PASSWORD)
    log(f"signed in as {SYSADMIN_EMAIL}")

    tenant = ensure_tenant(sysadmin)
    ensure_tenant_admin(sysadmin, tenant)

    tb = Api(BASE_URL)
    tb.login(TENANT_ADMIN_EMAIL, TENANT_ADMIN_PASSWORD)
    log(f"signed in as {TENANT_ADMIN_EMAIL}")

    profile = ensure_device_profile(tb)
    customer = ensure_customer(tb)
    user = ensure_customer_user(tb, customer)
    fleet = ensure_fleet(tb, profile, customer)
    device = fleet[0]
    dashboard = ensure_dashboard(tb, device, customer)
    clear_user_default_dashboard(tb, user)

    # The Command Center is the customer's landing page; /home resolves to it.
    command_centre = ensure_fleet_overview(tb, customer)
    set_home_dashboard(tb, customer, command_centre)

    log("")
    log("=" * 62)
    log("BoxTech IoT Platform is provisioned")
    log("=" * 62)
    log(f"  Web UI          : http://localhost:8080")
    log(f"  System admin    : {SYSADMIN_EMAIL} / {SYSADMIN_PASSWORD}")
    log(f"  Tenant admin    : {TENANT_ADMIN_EMAIL} / {TENANT_ADMIN_PASSWORD}")
    log(f"  Customer user   : {CUSTOMER_USER_EMAIL} / {CUSTOMER_USER_PASSWORD}")
    log(f"  Customer        : {CUSTOMER_TITLE}")
    log(f"  Device          : {DEVICE_NAME}")
    log(f"  Device token    : {DEVICE_TOKEN}")
    log(f"  Device id       : {device['id']['id']}")
    log(f"  Dashboard       : {DASHBOARD_TITLE}")
    log(f"  Alarm rules     : Overspeed > {OVERSPEED_LIMIT:.0f} km/h (CRITICAL), "
        f"Fuel < {LOW_FUEL_LIMIT:.0f}% (WARNING), Offline (MAJOR)")
    log("=" * 62)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # surfaced in `docker compose logs boxtech-provisioner`
        log(f"FAILED: {exc}")
        sys.exit(1)
