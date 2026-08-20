# BoxTech IoT Platform on the Red Hat OpenShift Developer Sandbox

Free deployment. No paid cloud resources, no credit card, no VM.

ThingsBoard is **never compiled on OpenShift**. GitHub Actions builds three
`linux/amd64` images, pushes them to GHCR, and OpenShift only pulls and runs
them.

```
GitHub Actions (4 vCPU / 16 GB)        OpenShift Sandbox (ns: muhammadumerrrrr-dev)
┌──────────────────────────┐           ┌──────────────────────────────────────┐
│ Dockerfile               │           │          Route (edge TLS)            │
│  stage 1: mvn + Angular  │  ghcr.io  │                 │                    │
│  stage 2: temurin JRE    │ ────────► │      Service boxtech-platform:8080   │
│ deploy/provision         │  public   │                 │                    │
│ deploy/simulator         │  images   │  ┌──────────────┴────────────────┐   │
└──────────────────────────┘           │  │ boxtech-platform (UI+REST+WS) │   │
                                       │  │ boxtech-postgres (PVC 5Gi)    │   │
                                       │  │ boxtech-simulator (HTTP)      │   │
                                       │  │ boxtech-provisioner (Job)     │   │
                                       │  └───────────────────────────────┘   │
                                       └──────────────────────────────────────┘
```

## Minimum services for the recruiter demo

Four workloads — three long-running plus one Job. Anything else was cut.

| Workload | Kind | Why it is required |
|---|---|---|
| `boxtech-postgres` | Deployment + PVC + Service | ThingsBoard's only datastore |
| `boxtech-platform` | Deployment + PVC + Service | UI, REST API and WebSocket, all on port 8080 |
| `boxtech-provisioner` | Job (runs once) | Creates tenant, customer, device, alarm rules, dashboard |
| `boxtech-simulator` | Deployment | Live GPS telemetry over HTTP |

**No reverse-proxy container.** The OpenShift Route *is* the front door and the
TLS terminator. Adding Caddy or nginx would be a second front door and would
waste Sandbox quota.

**No MQTT broker exposure.** `deploy/simulator/simulator.py:97` posts to
`/api/v1/{token}/telemetry` over HTTP, so the demo needs no raw TCP.

**No logs PVC.** The packaged `application/src/main/resources/logback.xml` has
only a `ConsoleAppender`, so nothing is written to `/var/log/boxtech`. Use
`oc logs` instead.

## Files in this directory

| File | Contents |
|---|---|
| `01-secret.yaml` | Postgres credentials, ThingsBoard sysadmin, demo account passwords |
| `02-configmap.yaml` | `boxtech-platform-config` (JVM, bind address, proxy headers) and `boxtech-demo-config` (tenant/device/simulator settings) |
| `03-pvc.yaml` | 5 Gi Postgres claim, 1 Gi platform `/data` claim |
| `04-postgres.yaml` | Postgres Deployment + Service |
| `05-platform.yaml` | Platform Deployment + Service, startup/readiness/liveness probes |
| `06-route.yaml` | The single public HTTPS Route |
| `07-provisioner-job.yaml` | One-shot provisioning Job |
| `08-simulator.yaml` | Simulator Deployment |
| `09-keepalive-cronjob.yaml` | **Optional.** Revives pods killed by the 12-hour reaper |
| `kustomization.yaml` | Sets the GHCR owner and tag in one place |

---

## Step 1 — Push the repository to GitHub

The project is not a git repository yet. From `boxtech-iot-platform/`:

```bash
git init -b main && git add . && git commit -m "BoxTech IoT Platform" && git remote add origin https://github.com/YOUR_GITHUB_USER/boxtech-iot-platform.git && git push -u origin main
```

A **public** repository is strongly recommended: GitHub Actions minutes are
unlimited for public repos, and GHCR storage and bandwidth for public packages
are unambiguously free.

Two inherited upstream ThingsBoard workflows —
`.github/workflows/check-configuration-files.yml` and
`license-header-format.yml` — also trigger on push and will probably fail on a
fork. They do not block the image build. Delete them if the red X bothers you.

## Step 2 — Build and publish the images

The workflow runs automatically on push to `main`, or manually from
**Actions → Build and push BoxTech images to GHCR → Run workflow**.

Expect **25–45 minutes** for `boxtech-iot-platform` and under a minute each for
the two helpers. Authentication uses the automatic `GITHUB_TOKEN`; there is no
personal access token and no repository secret to create.

**Then make the packages public — a manual step the workflow cannot perform.**
Packages inherit private visibility from a private repo, and this deployment
uses no pull secret. For each of the three packages:

> GitHub → your profile → **Packages** → select the package → **Package
> settings** → **Danger Zone** → **Change visibility** → **Public**

Verify anonymously before going near OpenShift:

```bash
docker manifest inspect ghcr.io/YOUR_GITHUB_USER/boxtech-iot-platform:4.4.0
```

## Step 3 — Point the manifests at your GHCR account

GHCR path segments must be lowercase.

```bash
sed -i 's|GHCR_OWNER|your-github-user-lowercase|g' deploy/openshift/*.yaml
```

## Step 4 — Log in and deploy

Get the token and server from the OpenShift console: your name, top right →
**Copy login command** → **Display Token**.

```bash
oc login --token=YOUR_TOKEN --server=YOUR_SERVER
```

```bash
oc project muhammadumerrrrr-dev
```

```bash
oc apply -k deploy/openshift/ -n muhammadumerrrrr-dev
```

Optional, and expected to fail if the Sandbox withholds RBAC — apply it
separately so a rejection cannot fail the rest:

```bash
oc apply -f deploy/openshift/09-keepalive-cronjob.yaml -n muhammadumerrrrr-dev
```

## Step 5 — Watch it come up

First boot runs the schema install and takes **3–6 minutes**.

```bash
oc get pods -n muhammadumerrrrr-dev -w
```

```bash
oc logs -f deploy/boxtech-platform -n muhammadumerrrrr-dev
```

Wait for `Started ThingsboardServerApplication`. Then confirm the provisioner
finished — its log prints the demo credentials, the device id and the alarm
thresholds:

```bash
oc logs job/boxtech-provisioner -n muhammadumerrrrr-dev
```

## Step 6 — Get the public URL

```bash
oc get route boxtech -n muhammadumerrrrr-dev -o jsonpath='https://{.spec.host}{"\n"}'
```

Roughly `https://boxtech-muhammadumerrrrr-dev.apps.CLUSTER.openshiftapps.com`.
OpenShift generates the hostname and serves a trusted wildcard certificate — no
DNS record, no domain purchase, no cert-manager.

---

## Verification

**Platform responds** — expect `200`:

```bash
curl -s -o /dev/null -w '%{http_code}\n' "$(oc get route boxtech -n muhammadumerrrrr-dev -o jsonpath='https://{.spec.host}')/login"
```

**UI and dashboard** — open the Route URL and sign in as
`demo.user@demologistics.com` / `Password123!`. The vehicle-tracking dashboard
is that user's landing page, set by `set_default_dashboard` in `provision.py`.

**Simulator** — a telemetry line every 2 seconds:

```bash
oc logs -f deploy/boxtech-simulator -n muhammadumerrrrr-dev
```

**Telemetry reached the database** — the map marker moves and the speed/fuel
gauges update on their own. Confirm server-side in the UI under **Devices →
Demo Vehicle GPS Tracker → Latest telemetry**; `latitude`, `longitude`, `speed`
and `fuel` should carry timestamps seconds old.

**WebSocket** — the dashboard updating live *is* the WebSocket test; ThingsBoard
pushes every value over `wss://`. To confirm the transport rather than infer it,
open browser DevTools → **Network** → **WS** filter and reload. Expect a
`101 Switching Protocols` on `/api/ws/plugins/telemetry?token=...`, staying open
with frames arriving every ~2 s. It must be `wss://` on the Route hostname — the
same origin as the page, which is what the single-Route design guarantees.

**Alarms** — the simulator drives speed past the 80 km/h limit and fuel below
20%, so a CRITICAL *Overspeed* and a WARNING *Low fuel* alarm should appear on
the dashboard's alarm widget within a few minutes.

---

## Sandbox limitations that affect this deployment

**1. Pods are deleted after 12 consecutive hours of runtime.** The Developer
Sandbox FAQ states this plainly, and it is *runtime-based, not traffic-based* —
keeping the demo busy does not prevent it. **A recruiter opening your link more
than 12 hours after you deploy will hit a 503.** This is the single biggest risk
to the deliverable. Mitigations, in order of preference:

- Scale the stack up **~10 minutes before** sharing the link.
- Apply `09-keepalive-cronjob.yaml` so the stack self-heals within 20 minutes.
- Re-run the wake-up command whenever needed.

Waking the demo:

```bash
oc scale deployment/boxtech-postgres deployment/boxtech-platform deployment/boxtech-simulator --replicas=1 -n muhammadumerrrrr-dev
```

**2. The sandbox itself expires after 30 days.** It is renewable and there is no
limit on how many times you may sign up, but a renewed sandbox is a *new*
namespace — PVCs do not survive. Re-apply and re-provision; it takes ~10 minutes.

**3. Arbitrary UID (restricted-v2 SCC).** Containers run as a random UID from
the namespace range with GID 0, ignoring the image's `USER`. Two consequences,
both already handled: the root `Dockerfile` grants group 0 owner-equivalent
rights, and Postgres uses `quay.io/sclorg/postgresql-16-c9s` rather than
`postgres:16-alpine`, which cannot start under a random UID because it cannot
write its socket directory. **Do not swap the Postgres image back.**

**4. Quota is roughly 3 cores / 14 GB RAM / 40 GB storage.** This deployment
requests 0.42 cores and 1.4 GB and caps at 2.3 cores and 4.5 GB — comfortably
inside it. Confirm what you actually have:

```bash
oc describe quota -n muhammadumerrrrr-dev && oc describe limitrange -n muhammadumerrrrr-dev
```

If a `LimitRange` caps per-container memory below 3 Gi, lower the platform limit
in `05-platform.yaml` and `JAVA_OPTS` in `02-configmap.yaml` **together** — the
heap must stay well under the container limit or the JVM is OOM-killed.

**5. PVC support varies.** RWO claims and a default StorageClass are normally
available. Check with `oc get storageclass`. If PVCs are refused entirely the
demo still runs on `emptyDir`, but **all telemetry is lost on every pod
restart** — and the `.installed` marker disappears with it, so the entrypoint
re-runs the schema installer against a populated database and the pod fails to
start. If you must go that route, switch **both** volumes to `emptyDir`, never
just one.

**6. No raw TCP ingress.** OpenShift Routes carry HTTP, HTTPS and TLS-SNI only,
so port 1883 cannot be published. Irrelevant for this demo (the simulator is
HTTP), but real MQTT devices could not connect to a Sandbox deployment.

**7. Build minutes.** The ~40-minute platform build consumes 40 of the 2,000
free monthly minutes on a private repo, and nothing on a public one.

---

## Resetting the demo

Both PVCs must go together — see the warning at the top of `03-pvc.yaml`. The
`.installed` marker on `boxtech-platform-data` and the schema on
`boxtech-postgres-data` are one unit; deleting either alone leaves the platform
unable to start.

```bash
oc delete -k deploy/openshift/ -n muhammadumerrrrr-dev && oc delete pvc boxtech-postgres-data boxtech-platform-data -n muhammadumerrrrr-dev
```

## Demo credentials

Set in `01-secret.yaml`, identical to the repository `docker-compose.yml`.

| Role | Email | Password |
|---|---|---|
| Customer user (dashboard) | `demo.user@demologistics.com` | `Password123!` |
| Tenant admin | `tenant@boxtech.io` | `BoxTech@2026` |
| System admin | `sysadmin@thingsboard.org` | `sysadmin` |

The system administrator account is created by the ThingsBoard installer with
its default password on an internet-facing deployment. **Change it in the UI
right after the first deploy**, or edit `01-secret.yaml` before applying.
