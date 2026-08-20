# Evaluator's Guide — BoxTech IoT Platform

A five-minute walkthrough for reviewing this submission against the Task 1 brief.
Full details are in [README.md](README.md).

---

## 1. Start it

```bash
docker compose up -d --build
```

Docker is the only prerequisite. The first build compiles the branded UI and the
platform from source, so allow **30–60 minutes**; subsequent runs start in about
a minute.

Follow the provisioning log — it prints a summary block and exits 0 when the
environment is ready:

```bash
docker compose logs -f boxtech-provisioner
```

If you would rather not build, load the exported image first and Compose will use
it instead of rebuilding:

```bash
docker load -i boxtech-iot-platform.tar.gz && docker compose up -d
```

---

## 2. Check it against the brief

Open **http://localhost:8080**.

| # | Brief asks for | Where to see it |
| :-- | :--- | :--- |
| 1 | Deployed with Docker | `docker compose ps` — four services: postgres, platform, provisioner (exited 0), simulator |
| 2 | Branded as BoxTech IoT Platform | Login page: BoxTech emblem, product name, green `#047241` theme. Browser tab: BoxTech title and favicon |
| 3 | One customer — Demo Logistics Company | Sign in as tenant admin → **Customers & users → Customers** |
| 4 | One customer user | Same page → Demo Logistics Company → **Users** → Demo Manager |
| 5 | One device — Demo Vehicle GPS Tracker | **Devices & assets → Devices**, assigned to Demo Logistics Company |
| 6 | GPS, speed, ignition, battery, fuel, temperature, online/offline | Open the device → **Latest telemetry**. Online/offline is the `active` attribute under **Attributes → Server attributes** |
| 7 | Vehicle tracking dashboard | Sign out, sign in as the customer user — it lands on the dashboard |
| 8 | Overspeed > 80 km/h and low fuel < 20 % alerts | Tenant admin → **Devices & assets → Device profiles → BoxTech Vehicle Tracker → Alarm rules** |

### Sign-in details

| Role | Username | Password |
| :--- | :--- | :--- |
| Customer user | `demo.user@demologistics.com` | `Password123!` |
| Tenant administrator | `tenant@boxtech.io` | `BoxTech@2026` |
| System administrator | `sysadmin@thingsboard.org` | `sysadmin` |

---

## 3. Watch the alarms work

This is the part worth spending two minutes on. The simulator runs a repeating
drive cycle that crosses the thresholds in both directions rather than sitting
past them, so alarms raise **and** clear while you watch:

| Phase | Duration | What you should see |
| :--- | :--- | :--- |
| Cruise | ~2 min | Speed oscillating around 58–78 km/h, no alarms |
| Overspeed | ~50 s | Speed climbs past 80 → **Overspeed Alert (CRITICAL)** appears |
| Idle | ~30 s | Speed 0, ignition off → the overspeed alarm clears |
| Signal loss | ~80 s | No telemetry → the device goes inactive → **Vehicle Offline (MAJOR)** |

**Low Fuel Alert (WARNING)** is on a slower cycle — fuel starts near 78 %, drains
while the engine runs, trips the alarm below 20 %, and clears on refuelling.

Follow along in the container log:

```bash
docker compose logs -f boxtech-simulator
```

---

## 4. Poke at the API

```bash
curl -s -X POST http://localhost:8080/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"tenant@boxtech.io\",\"password\":\"BoxTech@2026\"}"
```

Push a reading by hand — send `speed` above 80 and the CRITICAL alarm fires within
a second:

```bash
curl -s -X POST http://localhost:8080/api/v1/DEMO_VEHICLE_TRACKER_TOKEN/telemetry -H "Content-Type: application/json" -d "{\"speed\":118.4,\"fuel\":11.2}"
```

---

## 5. Tear it down

```bash
docker compose down -v
```

Removes the containers and the volumes. The next `up` reinstalls and re-provisions
from scratch — worth doing once if you want to confirm nothing was configured by
hand.
