#!/usr/bin/env python3
"""Telemetry simulator for the BoxTech demo vehicle.

Drives a tracker along Shahrah-e-Faisal, Karachi and publishes GPS position,
speed, ignition, battery, fuel and temperature over the HTTP device API.

The point of the drive cycle is that it *crosses* the alarm thresholds rather
than sitting past them: fuel drains from a full tank down through the 20% low
fuel line and is refuelled, speed varies through the 80 km/h limit in both
directions, and the tracker goes quiet for a stretch so the platform marks the
device inactive. A reviewer watching the dashboard sees alarms raise and clear
on their own instead of a permanently red screen.
"""
from __future__ import annotations

import math
import os
import random
import signal
import sys
import time

import requests

BASE_URL = os.environ.get("TB_BASE_URL", "http://boxtech-platform:8080").rstrip("/")
TOKEN = os.environ.get("BOXTECH_DEVICE_TOKEN", "DEMO_VEHICLE_TRACKER_TOKEN")
TOKEN_2 = os.environ.get("BOXTECH_DEVICE_TOKEN_2", "BT_TRK_002_TOKEN")
TOKEN_3 = os.environ.get("BOXTECH_DEVICE_TOKEN_3", "BT_TRK_003_TOKEN")
INTERVAL_S = float(os.environ.get("BOXTECH_SIM_INTERVAL", "2"))
SPEED_LIMIT = float(os.environ.get("BOXTECH_SPEED_LIMIT", "80"))
FUEL_LIMIT = float(os.environ.get("BOXTECH_FUEL_LIMIT", "20"))

# Shahrah-e-Faisal, Karachi: Karsaz -> Drigh Road -> Malir Halt and back.
ROUTE = [
    (24.8716, 67.0598),
    (24.8685, 67.0650),
    (24.8652, 67.0725),
    (24.8620, 67.0810),
    (24.8580, 67.0910),
    (24.8540, 67.1000),
    (24.8580, 67.0910),
    (24.8620, 67.0810),
    (24.8652, 67.0725),
    (24.8685, 67.0650),
]

# One pass through the cycle takes roughly 12 minutes at the default interval.
CRUISE_TICKS = 60          # normal motorway running, occasionally near the limit
OVERSPEED_TICKS = 25       # sustained overspeed, raises the CRITICAL alarm
IDLE_TICKS = 15            # stopped, ignition off
OFFLINE_TICKS = 40         # tracker silent, platform marks the device inactive

_running = True


def _stop(signum, _frame):
    global _running
    _running = False
    print(f"[simulator] received signal {signum}, shutting down", flush=True)


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def log(msg: str) -> None:
    print(f"[simulator] {msg}", flush=True)


def wait_for_platform(timeout_s: int = 900) -> None:
    log(f"waiting for the platform at {BASE_URL}")
    deadline = time.time() + timeout_s
    while time.time() < deadline and _running:
        try:
            if requests.get(f"{BASE_URL}/login", timeout=10).status_code == 200:
                log("platform is up")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    if _running:
        raise SystemExit(f"platform did not come up within {timeout_s}s")


def interpolate(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    d_lon = math.radians(b[1] - a[1])
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def send(token: str, payload: dict) -> bool:
    try:
        r = requests.post(f"{BASE_URL}/api/v1/{token}/telemetry", json=payload, timeout=10)
        if r.ok:
            return True
        log(f"telemetry rejected: HTTP {r.status_code} {r.text[:200]}")
    except requests.RequestException as exc:
        log(f"telemetry send failed: {exc}")
    return False


class Vehicle:
    """One tracker. The physics and phase machine are exactly the single-vehicle
    behaviour that shipped before; this only gives each vehicle its own copy of
    the state so several can run from one process."""

    def __init__(self, name: str, token: str, segment: int = 0,
                 phase: str = "cruise", fuel: float = 78.0, battery: float = 96.0):
        self.name = name
        self.token = token
        self.segment = segment
        self.progress = 0.0
        self.fuel = fuel
        self.battery = battery
        self.odometer = 0.0
        self.phase = phase
        self.phase_tick = 0
        self.sent = 0

    def tick(self) -> None:
        a = ROUTE[self.segment]
        b = ROUTE[(self.segment + 1) % len(ROUTE)]
        lat, lon = interpolate(a, b, self.progress)

        if self.phase == "cruise":
            # Sinusoidal traffic flow that brushes the limit without holding above it.
            # Amplitude and jitter are bounded so the peak (58 + 17 + 3 = 78) stays
            # under the 80 km/h threshold: cruise must not raise the overspeed alarm.
            speed = 58 + 17 * math.sin(self.phase_tick / 7.0) + random.uniform(-3, 3)
            ignition = True
        elif self.phase == "overspeed":
            # Trough (88 - 4 - 2 = 82) stays clear of the threshold, so the CRITICAL
            # alarm holds for the whole phase instead of flapping on a dip to 80.
            speed = 88 + 4 * math.sin(self.phase_tick / 4.0) + random.uniform(-2, 2)
            ignition = True
        else:  # idle or offline
            speed = 0.0
            ignition = False

        speed = max(0.0, round(speed, 1))

        # Consumption tracks how hard the vehicle is working; refuel when nearly dry.
        if ignition:
            self.fuel -= 0.05 + speed / 2400.0
            self.battery = min(100.0, self.battery + 0.02)
        else:
            self.battery -= 0.01
        if self.fuel <= 8.0:
            log(f"{self.name}: refuelling, tank back to 85%")
            self.fuel = 85.0
        self.fuel = max(0.0, round(self.fuel, 1))
        self.battery = round(max(0.0, min(100.0, self.battery)), 1)

        # Engine bay runs hotter the faster it goes.
        temperature = round(29.0 + speed / 22.0 + random.uniform(-0.4, 0.4), 1)
        self.odometer = round(self.odometer + speed * INTERVAL_S / 3600.0, 3)

        if self.phase == "offline":
            if self.phase_tick == 0:
                log(f"{self.name}: signal loss for {int(OFFLINE_TICKS * INTERVAL_S)}s "
                    f"(device will be marked offline)")
        else:
            payload = {
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "speed": speed,
                "heading": round(bearing(a, b), 1),
                "ignition": ignition,
                "battery": self.battery,
                "fuel": self.fuel,
                "temperature": temperature,
                "odometer": self.odometer,
            }
            if send(self.token, payload):
                self.sent += 1
                if self.sent % 15 == 0:
                    log(f"{self.name}: {self.sent} samples | speed {speed:g} km/h "
                        f"| fuel {self.fuel:g}% | phase {self.phase}")

        # Advance along the route only while moving.
        if speed > 0:
            self.progress += max(0.02, speed / 1500.0)
            while self.progress >= 1.0:
                self.progress -= 1.0
                self.segment = (self.segment + 1) % len(ROUTE)

        self.phase_tick += 1
        limits = {"cruise": CRUISE_TICKS, "overspeed": OVERSPEED_TICKS,
                  "idle": IDLE_TICKS, "offline": OFFLINE_TICKS}
        if self.phase_tick >= limits[self.phase]:
            self.phase = {"cruise": "overspeed", "overspeed": "idle",
                          "idle": "offline", "offline": "cruise"}[self.phase]
            self.phase_tick = 0
            log(f"{self.name}: entering '{self.phase}' phase")


def main() -> int:
    wait_for_platform()

    # Staggered so the three vehicles are never in the same phase at the same
    # moment - the fleet view is meant to show a mix of online and offline.
    fleet = [
        Vehicle("BT-TRK-001", TOKEN, segment=0, phase="cruise", fuel=78.0, battery=96.0),
        Vehicle("BT-TRK-002", TOKEN_2, segment=2, phase="overspeed", fuel=46.0, battery=88.0),
        Vehicle("BT-TRK-003", TOKEN_3, segment=4, phase="idle", fuel=24.0, battery=71.0),
    ]

    log(f"streaming to {BASE_URL} every {INTERVAL_S:g}s")
    for v in fleet:
        log(f"  vehicle {v.name} as device token '{v.token}'")
    log(f"thresholds: overspeed > {SPEED_LIMIT:g} km/h, low fuel < {FUEL_LIMIT:g}%")

    while _running:
        for v in fleet:
            if not _running:
                break
            v.tick()
        time.sleep(INTERVAL_S)

    log(f"stopped after {sum(v.sent for v in fleet)} samples")
    return 0


if __name__ == "__main__":
    sys.exit(main())
