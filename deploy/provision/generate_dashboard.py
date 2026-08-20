#!/usr/bin/env python3
"""Generate the BoxTech Vehicle Tracking dashboard definition.

Each widget starts from the shipped widget type's own ``defaultConfig`` (read out
of application/src/main/data/json/system/widget_types) and is then rebound from
the demo function datasource to the real device alias. Starting from the
platform's own defaults keeps the generated config schema-valid against whatever
version of the widget the platform ships.

Run from the repository root:

    python deploy/provision/generate_dashboard.py

Writes deploy/provision/dashboard_vehicle_tracking.json, which the provisioner
container uploads. The device id is not baked in: the provisioner substitutes
the DEVICE_ID placeholder at upload time.
"""
from __future__ import annotations

import copy
import json
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
WIDGET_TYPES = os.path.join(
    REPO, "application", "src", "main", "data", "json", "system", "widget_types"
)
OUT = os.path.join(HERE, "dashboard_vehicle_tracking.json")

BRAND = "#047241"
DANGER = "#d92d20"
WARN = "#f79009"
INFO = "#1570ef"
MUTED = "#475569"

# Replaced by the provisioner with the real device UUID.
DEVICE_ID_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"

ALIAS_ID = "b0c7e1a2-4f3d-4c8a-9e21-7d5f0a1b2c3d"
ALIAS_NAME = "Demo Vehicle"


def load_default_config(filename: str) -> dict:
    with open(os.path.join(WIDGET_TYPES, filename), encoding="utf-8") as f:
        wt = json.load(f)
    cfg = wt["descriptor"]["defaultConfig"]
    return json.loads(cfg) if isinstance(cfg, str) else copy.deepcopy(cfg)


def data_key(name: str, label: str, color: str, key_type: str = "timeseries", **extra) -> dict:
    key = {
        "name": name,
        "type": key_type,
        "label": label,
        "color": color,
        "settings": {},
        "aggregationType": None,
        "units": None,
        "decimals": None,
        "funcBody": None,
        "usePostProcessing": None,
        "postFuncBody": None,
    }
    key.update(extra)
    return key


def entity_datasource(keys: list[dict], name: str = ALIAS_NAME) -> list[dict]:
    return [{"type": "entity", "name": name, "entityAliasId": ALIAS_ID, "dataKeys": keys}]


def constant_color(color: str) -> dict:
    return {"type": "constant", "color": color, "colorFunction": None}


def range_color(color: str, ranges: list[dict]) -> dict:
    """A colour that switches on the value, e.g. red once speed passes 80."""
    return {"type": "range", "color": color, "colorFunction": None, "rangeList": ranges}


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

def value_card(
    *,
    title: str,
    key: str,
    label: str,
    units: str,
    decimals: int,
    icon: str,
    icon_color: dict,
    value_color: dict,
    key_type: str = "timeseries",
) -> tuple[str, dict]:
    cfg = load_default_config("value_card.json")
    cfg["datasources"] = entity_datasource([data_key(key, label, BRAND, key_type)])
    cfg["title"] = title
    cfg["showTitle"] = False
    cfg["units"] = units
    cfg["decimals"] = decimals
    s = cfg["settings"]
    s["layout"] = "square"
    s["labelPosition"] = "top"
    s["showLabel"] = True
    s["labelColor"] = constant_color(MUTED)
    s["showIcon"] = True
    s["icon"] = icon
    s["iconSize"] = 36
    s["iconColor"] = icon_color
    s["valueColor"] = value_color
    s["valueFont"]["size"] = 40
    s["showDate"] = True
    s["background"] = {
        "type": "color",
        "color": "#ffffff",
        "overlay": {"enabled": False, "color": "rgba(255,255,255,0.72)", "blur": 3},
    }
    return "system.cards.value_card", cfg


def map_widget() -> tuple[str, dict]:
    cfg = load_default_config("map.json")
    cfg["title"] = "Live Vehicle Location"
    cfg["showTitle"] = True
    cfg["showTitleIcon"] = True
    cfg["titleIcon"] = "location_on"
    cfg["iconColor"] = BRAND
    cfg["datasources"] = []

    marker = copy.deepcopy(cfg["settings"]["markers"][1])
    marker.update(
        {
            "dsType": "entity",
            "dsLabel": ALIAS_NAME,
            "dsDeviceId": None,
            "dsEntityAliasId": ALIAS_ID,
            "dsFilterId": None,
            "additionalDataKeys": [
                data_key("speed", "speed", BRAND),
                data_key("fuel", "fuel", WARN),
                data_key("ignition", "ignition", INFO),
                data_key("battery", "battery", MUTED),
            ],
            "label": {"show": True, "type": "pattern", "pattern": "${entityName}"},
            "tooltip": {
                "show": True,
                "trigger": "click",
                "autoclose": False,
                "type": "pattern",
                "pattern": (
                    "<b>${entityName}</b><br/>"
                    "<b>Speed:</b> ${speed} km/h<br/>"
                    "<b>Fuel:</b> ${fuel} %<br/>"
                    "<b>Battery:</b> ${battery} %<br/>"
                    "<b>Ignition:</b> ${ignition}<br/>"
                    "<b>Position:</b> ${latitude:5}, ${longitude:5}"
                ),
                "offsetX": 0,
                "offsetY": -1,
            },
            "xKey": data_key("latitude", "latitude", BRAND),
            "yKey": data_key("longitude", "longitude", BRAND),
            "markerType": "icon",
            "markerIcon": {
                "size": 40,
                "color": constant_color(BRAND),
                "icon": "local_shipping",
            },
        }
    )
    marker["markerClustering"]["enable"] = False
    cfg["settings"]["markers"] = [marker]
    cfg["settings"]["polygons"] = []
    cfg["settings"]["circles"] = []
    cfg["settings"]["additionalDataSources"] = []
    return "system.map", cfg


def time_series_chart() -> tuple[str, dict]:
    cfg = load_default_config("time_series_chart.json")
    cfg["title"] = "Speed & Fuel History"
    cfg["showTitle"] = True
    cfg["showTitleIcon"] = True
    cfg["titleIcon"] = "show_chart"
    cfg["iconColor"] = BRAND
    cfg["useDashboardTimewindow"] = True
    speed = data_key("speed", "Speed (km/h)", BRAND)
    speed["settings"] = {"type": "line", "lineWidth": 2, "showPoints": False}
    fuel = data_key("fuel", "Fuel (%)", WARN)
    fuel["settings"] = {"type": "line", "lineWidth": 2, "showPoints": False}
    cfg["datasources"] = entity_datasource([speed, fuel])
    cfg["settings"]["dataZoom"] = True
    cfg["settings"]["thresholds"] = []
    return "system.time_series_chart", cfg


def alarm_count() -> tuple[str, dict]:
    cfg = load_default_config("alarm_count.json")
    cfg["title"] = "Active Alarms"
    cfg["showTitle"] = False
    cfg["datasources"] = [
        {
            "type": "entity",
            "name": ALIAS_NAME,
            "entityAliasId": ALIAS_ID,
            "dataKeys": [],
            "alarmFilterConfig": {"statusList": ["ACTIVE"]},
        }
    ]
    return "system.alarm_count", cfg


def alarms_table() -> tuple[str, dict]:
    cfg = load_default_config("alarms_table.json")
    cfg["title"] = "Fleet Alarms"
    cfg["showTitle"] = True
    cfg["showTitleIcon"] = True
    cfg["titleIcon"] = "notification_important"
    cfg["iconColor"] = DANGER
    cfg["alarmSource"]["type"] = "entity"
    cfg["alarmSource"]["entityAliasId"] = ALIAS_ID
    cfg["alarmSource"]["name"] = ALIAS_NAME
    cfg["alarmSearchStatus"] = "ANY"
    cfg["settings"]["defaultPageSize"] = 8
    cfg["settings"]["alarmsTitle"] = "Fleet Alarms"
    return "system.alarm_widgets.alarms_table", cfg


# ---------------------------------------------------------------------------
# Dashboard assembly
# ---------------------------------------------------------------------------

# (builder, sizeX, sizeY, row, col) on the 24-column grid.
LAYOUT = [
    (
        lambda: value_card(
            title="Speed",
            key="speed",
            label="Speed",
            units="km/h",
            decimals=1,
            icon="speed",
            icon_color=range_color(BRAND, [{"from": 80, "to": None, "color": DANGER}]),
            value_color=range_color(
                "rgba(0, 0, 0, 0.87)", [{"from": 80, "to": None, "color": DANGER}]
            ),
        ),
        6, 3, 0, 0,
    ),
    (
        lambda: value_card(
            title="Fuel Level",
            key="fuel",
            label="Fuel Level",
            units="%",
            decimals=1,
            icon="local_gas_station",
            icon_color=range_color(BRAND, [{"from": None, "to": 20, "color": WARN}]),
            value_color=range_color(
                "rgba(0, 0, 0, 0.87)", [{"from": None, "to": 20, "color": WARN}]
            ),
        ),
        6, 3, 0, 6,
    ),
    (
        lambda: value_card(
            title="Battery",
            key="battery",
            label="Battery",
            units="%",
            decimals=1,
            icon="battery_charging_full",
            icon_color=range_color(BRAND, [{"from": None, "to": 25, "color": DANGER}]),
            value_color=constant_color("rgba(0, 0, 0, 0.87)"),
        ),
        6, 3, 0, 12,
    ),
    (
        lambda: value_card(
            title="Temperature",
            key="temperature",
            label="Temperature",
            units="°C",
            decimals=1,
            icon="thermostat",
            icon_color=constant_color(INFO),
            value_color=constant_color("rgba(0, 0, 0, 0.87)"),
        ),
        6, 3, 0, 18,
    ),
    (map_widget, 15, 10, 3, 0),
    (
        lambda: value_card(
            title="Ignition",
            key="ignition",
            label="Ignition",
            units="",
            decimals=0,
            icon="key",
            icon_color=constant_color(BRAND),
            value_color=constant_color("rgba(0, 0, 0, 0.87)"),
        ),
        9, 3, 3, 15,
    ),
    (
        lambda: value_card(
            title="Connectivity",
            key="active",
            label="Connectivity",
            units="",
            decimals=0,
            icon="wifi",
            icon_color=constant_color(BRAND),
            value_color=constant_color("rgba(0, 0, 0, 0.87)"),
            key_type="attribute",
        ),
        9, 3, 6, 15,
    ),
    (alarm_count, 9, 4, 9, 15),
    (time_series_chart, 14, 6, 13, 0),
    (alarms_table, 10, 6, 13, 14),
]

WIDGET_KIND = {
    "system.map": "latest",
    "system.cards.value_card": "latest",
    "system.alarm_count": "latest",
    "system.time_series_chart": "timeseries",
    "system.alarm_widgets.alarms_table": "alarm",
}


def build() -> dict:
    widgets: dict[str, dict] = {}
    layout_widgets: dict[str, dict] = {}

    for builder, size_x, size_y, row, col in LAYOUT:
        fqn, cfg = builder()
        wid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"boxtech/{fqn}/{row}/{col}"))
        widgets[wid] = {
            "type": WIDGET_KIND[fqn],
            "sizeX": size_x,
            "sizeY": size_y,
            "config": cfg,
            "id": wid,
            "typeFullFqn": fqn,
        }
        layout_widgets[wid] = {"sizeX": size_x, "sizeY": size_y, "row": row, "col": col}

    return {
        "title": "Vehicle Tracking Dashboard",
        "name": "Vehicle Tracking Dashboard",
        "image": None,
        "mobileHide": False,
        "mobileOrder": None,
        "configuration": {
            "widgets": widgets,
            "states": {
                "default": {
                    "name": "Vehicle Tracking",
                    "root": True,
                    "layouts": {
                        "main": {
                            "widgets": layout_widgets,
                            "gridSettings": {
                                "backgroundColor": "#f8fafc",
                                "color": "rgba(0,0,0,0.870588)",
                                "columns": 24,
                                "backgroundSizeMode": "100%",
                                "autoFillHeight": False,
                                "mobileAutoFillHeight": False,
                                "mobileRowHeight": 70,
                                "margin": 12,
                                "outerMargin": True,
                                "layoutType": "default",
                            },
                        }
                    },
                }
            },
            "entityAliases": {
                ALIAS_ID: {
                    "id": ALIAS_ID,
                    "alias": ALIAS_NAME,
                    "filter": {
                        "type": "singleEntity",
                        "resolveMultiple": False,
                        "singleEntity": {
                            "entityType": "DEVICE",
                            "id": DEVICE_ID_PLACEHOLDER,
                        },
                    },
                }
            },
            "filters": {},
            "timewindow": {
                "displayValue": "",
                "selectedTab": 0,
                "hideAggregation": False,
                "hideAggInterval": False,
                "realtime": {"interval": 1000, "timewindowMs": 900000},
                "history": {
                    "historyType": 0,
                    "interval": 1000,
                    "timewindowMs": 3600000,
                    "fixedTimewindow": {"startTimeMs": 0, "endTimeMs": 0},
                },
                "aggregation": {"type": "NONE", "limit": 25000},
            },
            "settings": {
                "stateControllerId": "entity",
                "showTitle": True,
                "showDashboardsSelect": True,
                "showEntitiesSelect": False,
                "showDashboardTimewindow": True,
                "showDashboardExport": True,
                "toolbarAlwaysOpen": True,
                "titleColor": "rgba(0,0,0,0.870588)",
                "showDashboardLogo": False,
                "dashboardLogoUrl": None,
                "hideToolbar": False,
                "showFilters": False,
                "showUpdateDashboardImage": True,
                "dashboardCss": "",
            },
        },
    }


if __name__ == "__main__":
    dashboard = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)
    n = len(dashboard["configuration"]["widgets"])
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes, {n} widgets)")
