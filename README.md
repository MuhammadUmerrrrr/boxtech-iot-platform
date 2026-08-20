# BoxTech IoT Platform

A white-labelled build of **ThingsBoard Community Edition 4.4.0**, rebranded as the
**BoxTech IoT Platform** and pre-configured as a fleet telemetry demo: one logistics
customer, one GPS tracker streaming live data along Shahrah-e-Faisal in Karachi, a
vehicle tracking dashboard, and alarm rules for overspeeding and low fuel.

Submitted for the BoxTech **IoT Engineer** practical evaluation (Task 1).

---

## Quick start

One command, from this directory:

```bash
docker compose up -d --build
```

Then open **http://localhost:8080** and sign in as the customer user.

> **First build takes a while.** The branded UI lives in the Angular sources under
> `ui-ngx/`, so the image is compiled from source (Maven + Yarn + an Angular
> production build) rather than pulled pre-built. Expect **30–60 minutes** and
> roughly 3 GB of dependency downloads on the first run; rebuilds are cached and
> take a couple of minutes. Nothing is needed on the host except Docker — no JDK,
> no Node, no Python.

Watch it come up:

```bash
docker compose logs -f boxtech-provisioner
```

The stack is ready when the provisioner prints its summary block and exits 0.

---

## Sign-in details

| Role | Username | Password | Sees |
| :--- | :--- | :--- | :--- |
| **Customer user** | `demo.user@demologistics.com` | `Password123!` | The vehicle tracking dashboard (lands on it directly) |
| **Tenant administrator** | `tenant@boxtech.io` | `BoxTech@2026` | Devices, device profiles, alarm rules, dashboards, customers |
| **System administrator** | `sysadmin@thingsboard.org` | `sysadmin` | Tenants and platform settings |

| Endpoint | URL |
| :--- | :--- |
| Web UI | http://localhost:8080 |
| REST API | http://localhost:8080/api — `POST /api/auth/login`, then `X-Authorization: Bearer <token>` |
| Device telemetry (HTTP) | `POST http://localhost:8080/api/v1/DEMO_VEHICLE_TRACKER_TOKEN/telemetry` |
| MQTT | `localhost:1883`, username = the device access token |
| CoAP | `localhost:5683/udp` |

---

## What the stack contains

`docker compose up` starts four services:

| Service | Role |
| :--- | :--- |
| `postgres` | PostgreSQL 16 — entities and time series |
| `boxtech-platform` | The branded platform, built from this source tree |
| `boxtech-provisioner` | One-shot container that creates every demo entity over REST, then exits |
| `boxtech-simulator` | Streams live vehicle telemetry for as long as the stack runs |

Nothing is created by hand. Tearing the stack down and bringing it back up
reproduces an identical environment.

### Provisioned automatically

- **Tenant** — BoxTech Logistics, with the tenant administrator above.
- **Customer** — Demo Logistics Company (Karachi, Pakistan).
- **Customer user** — Demo Manager, landing straight on the tracking dashboard.
- **Device profile** — *BoxTech Vehicle Tracker*, carrying all three alarm rules.
- **Device** — Demo Vehicle GPS Tracker, access token `DEMO_VEHICLE_TRACKER_TOKEN`,
  assigned to the customer, 60-second inactivity timeout.
- **Dashboard** — Vehicle Tracking Dashboard, assigned to the customer.

### Alarm rules

| Alarm | Severity | Raised when | Cleared when |
| :--- | :--- | :--- | :--- |
| Overspeed Alert | `CRITICAL` | `speed` > 80 km/h | `speed` ≤ 80 km/h |
| Low Fuel Alert | `WARNING` | `fuel` < 20 % | `fuel` ≥ 20 % |
| Vehicle Offline | `MAJOR` | device inactive | device reporting again |

### Telemetry

The simulator publishes `latitude`, `longitude`, `speed`, `heading`, `ignition`,
`battery`, `fuel`, `temperature` and `odometer` every 2 seconds, and the platform
maintains the `active` attribute for online/offline state.

It runs a repeating drive cycle that deliberately **crosses** each threshold rather
than parking past it — cruise → sustained overspeed → idle with ignition off →
signal loss → cruise. Fuel drains through the 20 % line and is refuelled. So the
alarms raise *and* clear on their own while you watch, instead of showing a
permanently red dashboard.

---

## Branding

Applied in the Angular sources, so it is compiled into the served application:

- Platform name and page title (`BoxTech IoT Platform`), and every ThingsBoard
  mention in the English locale.
- BoxTech logo — horizontal lockup in the toolbar, emblem-only in the collapsed
  sidebar, with white variants for dark surfaces.
- Multi-resolution favicon and an Apple touch icon generated from the logo.
- Brand palette `#047241` wired through the Material theme and the shared SCSS
  tokens in `ui-ngx/src/scss/constants.scss`.
- Branded login page: emblem, product name, brand dot-grid background.

ThingsBoard Community Edition has no white-labelling feature — that is a
Professional Edition capability — which is why the branding is a source-level
change and why the image is built from source.

---

## Common tasks

```bash
docker compose logs -f boxtech-simulator
```

```bash
docker compose down
```

```bash
docker compose down -v
```

`down -v` also drops the volumes, so the next `up` reinstalls the schema and
re-provisions from scratch.

### Rebuild after changing the UI

```bash
docker compose up -d --build boxtech-platform
```

### Export the image for offline delivery

```bash
docker save boxtech/iot-platform:4.4.0 | gzip > boxtech-iot-platform.tar.gz
```

The recipient loads it with `docker load -i boxtech-iot-platform.tar.gz`, then
runs `docker compose up -d` (Compose reuses the loaded image instead of rebuilding).

---

## Repository layout

| Path | What it is |
| :--- | :--- |
| `Dockerfile` | Multi-stage build: Maven + Yarn → `eclipse-temurin:25-jre` |
| `docker-compose.yml` | The four-service evaluation stack |
| `deploy/platform/entrypoint.sh` | Waits for Postgres, installs the schema once, starts the server |
| `deploy/provision/provision.py` | Idempotent REST provisioning of every demo entity |
| `deploy/provision/generate_dashboard.py` | Regenerates the dashboard definition from the shipped widget types |
| `deploy/simulator/simulator.py` | The drive-cycle telemetry simulator |
| `ui-ngx/` | Angular front end, where the branding lives |
| `application/`, `common/`, `dao/`, … | Upstream ThingsBoard modules, unmodified |

---

## Running without Docker

Requires JDK 25, Node 22 and a PostgreSQL database.

```bash
mvn clean install -DskipTests -Dpkg.skip.deb=true -Dpkg.skip.rpm=true -Dpkg.skip.zip=true
```

```bash
java -cp application/target/thingsboard-4.4.0-SNAPSHOT-boot.jar -Dloader.main=org.thingsboard.server.ThingsboardInstallApplication -Dinstall.load_demo=false org.springframework.boot.loader.launch.PropertiesLauncher
```

```bash
java -cp application/target/thingsboard-4.4.0-SNAPSHOT-boot.jar -Dloader.main=org.thingsboard.server.ThingsboardServerApplication org.springframework.boot.loader.launch.PropertiesLauncher
```

Then provision and stream telemetry against it:

```bash
pip install requests && TB_BASE_URL=http://localhost:8080 python deploy/provision/provision.py
```

```bash
TB_BASE_URL=http://localhost:8080 python deploy/simulator/simulator.py
```

---

## Licence and attribution

This project is a customisation of
[ThingsBoard Community Edition](https://github.com/thingsboard/thingsboard),
© The ThingsBoard Authors, licensed under the Apache License 2.0. See `LICENSE`.
The BoxTech branding, the Docker deployment under `deploy/`, and the provisioning
and simulation tooling are the additions made for this evaluation.
