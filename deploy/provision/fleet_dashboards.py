"""BoxTech Fleet Command Center dashboard.

Ported from the recruiter-task implementation. The widget configurations are
read from the running platform's own widget catalogue rather than from local
widget-type files, which is how the original built them - a widget's
defaultConfig is the contract, and taking it from the live server means the
dashboard cannot drift away from the platform it is installed on.

Only the fleet view is built here. The per-vehicle details state is a separate
migration phase; the fleet dashboard is self-contained without it.

Colours follow the deployed BoxTech palette (#047241), not the palette the
original used - the branding in this repository is the one the submission
documents, and the dashboard has to match the shell it sits in.
"""

from __future__ import annotations

import json
import os
import random
import uuid

# Mirrors the configuration provision.py reads, so the two agree without one
# importing the other.
PROFILE_NAME = os.environ.get("BOXTECH_DEVICE_PROFILE", "BoxTech Vehicle Tracker")
CUSTOMER_TITLE = os.environ.get("BOXTECH_CUSTOMER_TITLE", "Demo Logistics Company")
SPEED_LIMIT = float(os.environ.get("BOXTECH_SPEED_LIMIT", "80"))
FUEL_LIMIT = float(os.environ.get("BOXTECH_FUEL_LIMIT", "20"))

FLEET_DASHBOARD_TITLE = "BoxTech Fleet Command Center"

# BoxTech palette, matching ui-ngx/src/scss/constants.scss.
BRAND = "#047241"           # primary green - values and type
ACCENT = "#078f52"          # lighter green - icons and highlights
CANVAS = "#f4f6f5"          # page background
SURFACE = "#ffffff"         # card background
MUTED = "#64748b"           # secondary type
HAIRLINE = "#e2e8f0"        # card borders
CRITICAL_COLOR = "#DC2626"
WARNING_COLOR = "#F59E0B"

def font(size, weight="500"):
    return {"family": "Roboto", "size": size, "sizeUnit": "px",
            "style": "normal", "weight": weight}


# Shared chrome so every widget reads as one surface rather than nine.

CARD_STYLE = {
    "borderRadius": "14px",
    "border": "1px solid " + HAIRLINE,
    "boxShadow": "0 1px 2px rgba(15,23,42,0.04), 0 10px 24px rgba(15,23,42,0.05)",
}

TITLE_STYLE = {
    "fontFamily": "Roboto",
    "fontSize": "13px",
    "fontWeight": "600",
    "letterSpacing": "0.03em",
    "textTransform": "uppercase",
    "color": MUTED,
}

def color_const(hex_value):
    return {"type": "constant", "color": hex_value, "colorFunction": ""}

def color_fn(js, fallback):
    """A colour that is recomputed from the live value on every update."""
    return {"type": "function", "color": fallback, "colorFunction": js}

def data_key(name, label, color, key_type="timeseries", units=None, decimals=None):
    key = {
        "name": name,
        "type": key_type,
        "label": label,
        "color": color,
        "settings": {},
        "_hash": random.random(),
        "aggregationType": None,
        "units": units,
        "decimals": decimals,
        "funcBody": None,
        "usePostProcessing": None,
        "postFuncBody": None,
    }
    return key

def datasource(alias_id, keys):
    return [{
        "type": "entity",
        "name": None,
        "entityAliasId": alias_id,
        "filterId": None,
        "dataKeys": keys,
    }]

def fleet_alias(alias_id, name):
    """An alias over every tracker of the BoxTech profile.

    Filtering by device type rather than listing entity ids means a vehicle
    added later appears on the overview without the dashboard being touched.
    """
    return {
        "id": alias_id,
        "alias": name,
        "filter": {
            "type": "deviceType",
            "resolveMultiple": True,
            "deviceTypes": [PROFILE_NAME],
            "deviceNameFilter": "",
        },
    }

def status_filter(filter_id, name, active):
    """A dashboard filter on the platform's own online/offline attribute.

    This has to be a dashboard filter rather than key filters on the alias.
    The entity count query only honours keyFilters at the top level of the
    query; the same filters written inside an alias's entityFilter are parsed
    and then ignored, so every count comes back as the unfiltered total.

    The shape below is the dashboard's FilterInfo model, which is *not* the
    shape the REST count endpoint takes. FilterInfo.keyFilters is an array of
    KeyFilterInfo, and each of those carries a plural `predicates` array whose
    entries wrap the real predicate under `keyFilterPredicate`. The UI converts
    that into the flat form the API wants, in filterInfoToKeyFilters().

    Writing the flat API form here parses fine and passes an API-level test, but
    the browser then iterates keyFilterInfo.predicates, finds undefined, throws,
    and the datasource never resolves - so the tile spins on its loading state
    forever while the same query returns the right number over REST.

    The optional `value` field is deliberately absent, and that matters more
    than it looks. Widgets do not use the REST endpoint at runtime; they open an
    ENTITY_COUNT subscription over the websocket, and the two transports do not
    deserialise identically. Setting `value: None` here survives REST but makes
    the websocket answer:

        {"errorCode": 2, "errorMsg": "Failed to parse the payload"}

    because filterInfoToKeyFilters() copies the null straight onto the KeyFilter
    it sends. Leaving the key out entirely makes it undefined, JSON.stringify
    drops it, and the command parses. Verified by replaying the exact websocket
    command both ways: with `value: null` it fails, without it the count returns.
    """
    return {
        "id": filter_id,
        "filter": name,
        "editable": False,
        "keyFilters": [{
            "key": {"type": "ATTRIBUTE", "key": "active"},
            "valueType": "BOOLEAN",
            "predicates": [{
                "keyFilterPredicate": {
                    "type": "BOOLEAN",
                    "operation": "EQUAL",
                    "value": {"defaultValue": active, "dynamicValue": None},
                },
                "userInfo": {
                    "editable": False,
                    "label": "",
                    "autogeneratedLabel": True,
                    "order": 0,
                },
            }],
        }],
    }


# Longitude bands along the demo corridor, west to east. Derived from the
# vehicle's own reported position - no lookup, no network, no stored city
# attribute. The names are the ones OpenStreetMap actually carries for these
# stretches of road; the compass qualifiers are descriptive, not invented
# landmarks.

LOCATION_JS = """
var lon = Number(value);
if (!isFinite(lon)) { return '&mdash;'; }
var where;
if (lon < 67.09)       { where = 'Shahrah-e-Faisal &middot; West'; }
else if (lon < 67.131) { where = 'Shahrah-e-Faisal &middot; Central'; }
else if (lon < 67.141) { where = 'Natha Khan Bridge'; }
else if (lon < 67.160) { where = 'Shahrah-e-Faisal (Drigh Road)'; }
else                   { where = 'Shahrah-e-Faisal &middot; East'; }
return '<span style="color:#047241">Karachi</span>'
     + '<span style="color:#64748b"> &middot; ' + where + '</span>';
"""

PILL_JS = """
function pill(text, bg, fg) {
  return '<span style="display:inline-block;padding:2px 9px;border-radius:999px;'
       + 'font:700 10px/1.6 Roboto,sans-serif;letter-spacing:.06em;'
       + 'background:' + bg + ';color:' + fg + '">' + text + '</span>';
}
"""

DONUT_JS = """
function donut(value, max, colour, label, sub) {
  var pct = Math.max(0, Math.min(1, value / max));
  var r = 17, c = 2 * Math.PI * r, dash = (pct * c).toFixed(1);
  return '<div style="display:flex;align-items:center;gap:9px">'
    + '<svg width="44" height="44" viewBox="0 0 44 44" style="flex:none">'
    +   '<circle cx="22" cy="22" r="' + r + '" fill="none" stroke="#EDEAE4" stroke-width="4"/>'
    +   '<circle cx="22" cy="22" r="' + r + '" fill="none" stroke="' + colour + '"'
    +     ' stroke-width="4" stroke-linecap="round"'
    +     ' stroke-dasharray="' + dash + ' ' + (c - dash).toFixed(1) + '"'
    +     ' transform="rotate(-90 22 22)"/>'
    +   '<text x="22" y="24" text-anchor="middle" '
    +     'style="font:700 12px Roboto,sans-serif;fill:' + colour + '">' + label + '</text>'
    + '</svg>'
    + (sub ? '<span style="font:400 10px Roboto,sans-serif;color:#64748b">' + sub + '</span>' : '')
    + '</div>';
}
"""

def style_widget(cfg, title_icon=None):
    cfg["backgroundColor"] = SURFACE
    cfg["padding"] = "10px"
    cfg["margin"] = "0px"
    cfg["dropShadow"] = False
    cfg["enableFullscreen"] = True
    cfg["widgetStyle"] = dict(CARD_STYLE)
    cfg["titleStyle"] = dict(TITLE_STYLE)
    if title_icon:
        cfg["showTitleIcon"] = True
        cfg["titleIcon"] = title_icon
        cfg["iconColor"] = ACCENT
        cfg["iconSize"] = "18px"
    return cfg

def kpi_wave_css(colour):
    """Decorative trend band along the bottom of a KPI card.

    This is ornament, not data. Counts have no history in the platform - there
    is no stored series for "how many vehicles were online an hour ago" - so
    nothing here is derived from telemetry and nothing is claimed to be. It is a
    fixed SVG path drawn as a CSS background so the cards match the reference
    console, with no axis, no scale and no gridlines that would suggest a plot.

    Delivered through the widget's own widgetCss field, so it needs no Angular
    change and no extra subscription.
    """
    stroke = colour.replace("#", "%23")
    fill = colour.replace("#", "%23")
    svg = (
        "data:image/svg+xml;utf8,"
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 60' preserveAspectRatio='none'>"
        f"<path d='M0,40 C40,22 70,50 110,34 C150,18 180,46 220,30"
        f" C260,14 290,42 330,28 C360,18 380,32 400,26 L400,60 L0,60 Z'"
        f" fill='{fill}' fill-opacity='0.10'/>"
        f"<path d='M0,40 C40,22 70,50 110,34 C150,18 180,46 220,30"
        f" C260,14 290,42 330,28 C360,18 380,32 400,26'"
        f" fill='none' stroke='{stroke}' stroke-opacity='0.55' stroke-width='2.5'/>"
        "</svg>"
    )
    return (
        ".tb-widget-container, .tb-widget {"
        f" background-image: url(\"{svg}\");"
        " background-repeat: no-repeat;"
        " background-position: bottom center;"
        " background-size: 100% 34px;"
        "}"
    )

def widget_catalogue(tb):
    """Widget type descriptors from the running platform.

    The catalogue carries its own Api handle so make_widget() and the builders
    below keep the signatures they had in the original implementation.
    """
    items = tb.get("/api/widgetTypes?pageSize=1000&page=0")["data"]
    return {"api": tb, "types": {w["fqn"]: w for w in items}}

def widget_descriptor(catalogue, fqn):
    entry = catalogue["types"].get(fqn)
    if not entry:
        raise RuntimeError(f"widget type '{fqn}' is not available on this platform")
    full = catalogue["api"].get(f"/api/widgetType/{entry['id']['id']}")
    desc = full["descriptor"]
    return desc, json.loads(desc["defaultConfig"])

def make_widget(catalogue, fqn, title, alias_id, keys, size,
                settings=None, title_icon=None, show_title=True):
    desc, cfg = widget_descriptor(catalogue, fqn)
    cfg["datasources"] = datasource(alias_id, keys)
    cfg["title"] = title
    cfg["showTitle"] = show_title
    if settings:
        cfg.setdefault("settings", {}).update(settings)
    style_widget(cfg, title_icon)
    return {
        "id": str(uuid.uuid4()),
        "typeFullFqn": f"system.{fqn}",
        "type": desc["type"],
        "sizeX": size[0],
        "sizeY": size[1],
        "config": cfg,
    }

def count_tile(catalogue, alias_id, label, icon, colour, size=(6, 3), filter_id=None,
               caption=None, wave=None):
    """A headline count. Uses the entityCount datasource, which counts matching
    entities rather than reading a telemetry key off one of them.

    filter_id points at a dashboard filter; that is the only place a condition
    on the count actually takes effect.
    """
    w = make_widget(catalogue, "entity_count", label, alias_id, [], size,
                    title_icon=icon, show_title=False)
    w["config"]["datasources"] = [{
        "type": "entityCount",
        "name": None,
        "entityAliasId": alias_id,
        "filterId": filter_id,
        "dataKeys": [{
            "name": "count", "type": "count", "label": label,
            "color": colour, "settings": {}, "_hash": random.random(),
        }],
    }]
    w["config"]["settings"].update({
        "showLabel": True, "label": label,
        "labelFont": font(13, "500"), "labelColor": color_const(MUTED),
        "showIcon": True, "icon": icon, "iconSize": 28, "iconSizeUnit": "px",
        "iconColor": color_const(colour),
        "showIconBackground": True, "iconBackgroundSize": 46,
        "iconBackgroundSizeUnit": "px",
        "iconBackgroundColor": color_const("#e6f1ec"),
        "valueFont": font(38, "600"), "valueColor": color_const(colour),
        "layout": "horizontal",
    })
    if caption:
        # The small line under the number on the reference cards.
        w["config"]["settings"]["showChevron"] = False
        w["config"]["title"] = caption
        w["config"]["showTitle"] = False
    if wave:
        w["config"]["widgetCss"] = kpi_wave_css(wave)
        # Room at the bottom so the number never sits on top of the band.
        w["config"]["padding"] = "10px 10px 26px"
    return w

def command_centre_header(catalogue, alias_id):
    """The masthead. A markdown card rather than a new Angular component: it
    needs no build, no dependency, and carries its own scoped CSS."""
    w = make_widget(catalogue, "cards.markdown_card", "Header", alias_id, [], (24, 3),
                    show_title=False)
    w["config"]["settings"] = {
        "useMarkdownTextFunction": False,
        "applyDefaultMarkdownStyle": False,
        "markdownTextPattern": (
            '<div class="bt-hd">'
            '<div class="bt-hd-main">'
            '<div class="bt-hd-title">FLEET COMMAND CENTER</div>'
            f'<div class="bt-hd-sub">{CUSTOMER_TITLE}</div>'
            '</div>'
            '<div class="bt-hd-tag">Your fleet at a glance</div>'
            '</div>'
        ),
        "markdownCss": (
            ".bt-hd{display:flex;align-items:center;justify-content:space-between;"
            "gap:16px;height:100%;padding:4px 6px}"
            ".bt-hd-main{display:flex;flex-direction:column;gap:4px;"
            "border-left:4px solid " + ACCENT + ";padding-left:14px}"
            ".bt-hd-title{font:700 22px/1.1 Roboto,sans-serif;letter-spacing:.06em;"
            "color:" + BRAND + "}"
            ".bt-hd-sub{font:500 13px/1.2 Roboto,sans-serif;letter-spacing:.02em;"
            "color:" + MUTED + "}"
            ".bt-hd-tag{font:400 12px/1.2 Roboto,sans-serif;color:" + MUTED + ";"
            "background:#e6f1ec;border:1px solid " + HAIRLINE + ";border-radius:999px;"
            "padding:6px 14px;white-space:nowrap}"
        ),
    }
    style_widget(w["config"])
    return w


# Shared status vocabulary. Kept as one string so the table, the map and the
# alert list cannot drift into using different words or colours for the same
# state - which is what makes a dashboard read as assembled rather than designed.

def build_map(catalogue, map_fqn, alias_id, ds_label="Fleet"):
    """Live position with a vehicle marker that turns red while overspeeding."""
    position_keys = [
        data_key("latitude", "latitude", BRAND),
        data_key("longitude", "longitude", BRAND),
    ]
    context_keys = [
        data_key("speed", "speed", BRAND, units="km/h", decimals=1),
        data_key("fuel", "fuel", WARNING_COLOR, units="%", decimals=1),
        data_key("battery", "battery", BRAND, units="%", decimals=1),
        data_key("temperature", "temperature", BRAND, units="°C", decimals=1),
        data_key("ignition", "ignition", BRAND),
        data_key("heading", "heading", BRAND, units="°", decimals=0),
    ]

    widget = make_widget(
        catalogue, map_fqn,
        "Live vehicle position — Shahrah-e-Faisal, Karachi", alias_id,
        position_keys + context_keys, (17, 16), title_icon="my_location")

    marker = {
        "dsType": "entity",
        "dsLabel": ds_label,
        "dsDeviceId": None,
        "dsEntityAliasId": alias_id,
        "dsFilterId": None,
        "additionalDataKeys": context_keys,
        "xKey": position_keys[0],
        "yKey": position_keys[1],
        "markerType": "icon",
        "markerShape": {"shape": "markerShape1", "size": 34, "color": color_const(BRAND)},
        "markerIcon": {
            "icon": "mdi:truck",
            "size": 44,
            "sizeUnit": "px",
            # The marker itself carries the alarm state, so the vehicle is
            # visibly red on the map the moment it crosses the speed limit.
            "color": color_fn(
                "var speed = data.speed;\n"
                f"if (speed !== undefined && speed > {SPEED_LIMIT:.0f}) {{ return '{CRITICAL_COLOR}'; }}\n"
                "if (data.ignition === false || data.ignition === 'false') { return '" + MUTED + "'; }\n"
                f"return '{BRAND}';", BRAND),
        },
        "markerOffsetX": 0.5,
        "markerOffsetY": 0.5,
        "label": {"show": True, "type": "pattern",
                  "pattern": "${entityName} — ${speed:0} km/h"},
        "tooltip": {
            "show": True,
            "trigger": "hover",
            "autoclose": False,
            "type": "pattern",
            "pattern": (
                "<div style=\"font:600 13px Roboto;color:" + BRAND + "\">${entityName}</div>"
                "<div style=\"font:400 12px Roboto;color:" + MUTED + ";margin-top:4px\">"
                "Speed <b>${speed:1} km/h</b><br/>"
                "Fuel <b>${fuel:1} %</b><br/>"
                "Battery <b>${battery:1} %</b><br/>"
                "Temperature <b>${temperature:1} °C</b><br/>"
                "Ignition <b>${ignition}</b><br/>"
                "Position <b>${latitude:5}, ${longitude:5}</b></div>"),
        },
        "groups": [],
    }

    widget["config"]["settings"].update({
        "mapType": "geoMap",
        "markers": [marker],
        "polygons": [],
        "circles": [],
        "additionalDataSources": [],
    })
    return widget


VEHICLE_STATE_ID = "vehicle_details"

CHART_TIMEWINDOW = {
    "hideInterval": True, "hideLastInterval": True, "hideQuickInterval": True,
    "hideAggregation": True, "hideAggInterval": True, "hideTimezone": True,
    "selectedTab": 0,
    "realtime": {"realtimeType": 0, "interval": 5000, "timewindowMs": 1800000},
    "aggregation": {"type": "NONE", "limit": 5000},
}

def open_details_action(name="Open vehicle details"):
    """Drill-down into the per-vehicle state, carrying the clicked entity.

    setEntityId is what makes the details state resolve to the vehicle that was
    clicked rather than to a fixed device.
    """
    return [{
        "id": str(uuid.uuid4()),
        "name": name,
        "icon": "open_in_new",
        "type": "openDashboardState",
        "targetDashboardStateId": VEHICLE_STATE_ID,
        "setEntityId": True,
        "stateEntityParamName": None,
        "openRightLayout": False,
        "openInSeparateDialog": False,
        "openInPopover": False,
    }]

def state_entity_alias(alias_id):
    """Resolves to whichever vehicle the details state was opened with."""
    return {
        "id": alias_id,
        "alias": "Selected vehicle",
        "filter": {
            "type": "stateEntity",
            "resolveMultiple": False,
            "stateEntityParamName": None,
            "defaultStateEntity": None,
        },
    }

def gauge_widget(catalogue, fqn, alias_id, key, unit_title, units, min_v, max_v,
                 highlights, size, title, title_icon):
    """An analogue dial with the alarm threshold painted onto the scale."""
    widget = make_widget(
        catalogue, fqn, title, alias_id,
        [data_key(key, unit_title, ACCENT, units=units, decimals=1)],
        size, title_icon=title_icon)
    widget["config"]["settings"].update({
        "minValue": min_v,
        "maxValue": max_v,
        # The band is the point: the operator sees where the limit sits on the
        # dial, not just the current number.
        "highlights": highlights,
        "highlightsWidth": 12,
        "showUnitTitle": True,
        "unitTitle": unit_title,
        "titleFont": {"family": "Roboto", "size": 16, "style": "normal", "weight": "600"},
        "titleColor": BRAND,
        "unitsFont": {"family": "Roboto", "size": 14, "style": "normal", "weight": "500"},
        "unitsColor": MUTED,
        "numbersFont": {"family": "Roboto", "size": 16, "style": "normal", "weight": "500"},
        "numbersColor": MUTED,
        "valueBox": True,
        "valueFont": {"family": "Roboto", "size": 28, "style": "normal", "weight": "600"},
        "valueColor": BRAND,
        "colorPlate": SURFACE,
        "colorMajorTicks": BRAND,
        "colorMinorTicks": HAIRLINE,
        "defaultColor": BRAND,
        "colorNeedle": BRAND,
        "colorNeedleEnd": BRAND,
        "colorValueBoxBackground": SURFACE,
        "colorValueBoxRect": HAIRLINE,
        "colorValueBoxRectEnd": HAIRLINE,
    })
    return widget

def metric_card(catalogue, fqn, alias_id, key, label, icon, units, decimals,
                value_color, icon_color=None):
    """A KPI tile: big number, unit, icon, and a colour that reacts to the value."""
    card = make_widget(
        catalogue, fqn, label, alias_id,
        [data_key(key, label, BRAND, units=units, decimals=decimals)],
        (6, 3), show_title=False)
    card["config"]["settings"].update({
        "layout": "square",
        "labelPosition": "top",
        # The widget title already names the reading. Repeating it as a tiny
        # in-card label, with a "last update" line under it, produced two lines
        # of unreadable grey text above the value and made the tiles look busy
        # and empty at the same time. The value is the point; give it the room.
        "showLabel": False,
        "labelFont": font(13, "500"),
        "labelColor": color_const(MUTED),
        "showIcon": True,
        "icon": icon,
        "iconSize": 34,
        "iconSizeUnit": "px",
        "iconColor": icon_color or color_const(ACCENT),
        "valueFont": font(40, "600"),
        "valueColor": value_color,
        "showDate": False,
        "dateFormat": {"format": None, "lastUpdateAgo": True, "custom": False},
        "dateFont": font(11, "400"),
        "dateColor": color_const(MUTED),
    })
    return card

def history_chart(catalogue, alias_id, title, icon, keys):
    """A fixed 30-minute chart. useDashboardTimewindow stays false so the
    dashboard toolbar can remain hidden."""
    w = make_widget(catalogue, "line_chart", title, alias_id, keys, (24, 7),
                    title_icon=icon)
    w["config"]["useDashboardTimewindow"] = False
    w["config"]["displayTimewindow"] = False
    w["config"]["timewindow"] = json.loads(json.dumps(CHART_TIMEWINDOW))
    return w

def vehicle_identity_header(catalogue, alias_id):
    """Masthead for the details state: who, what state, and where.

    Uses markdownTextFunction rather than a pattern because the status pills and
    the corridor both need logic, and the attributes card underneath has no
    content-function hook of its own.
    """
    w = make_widget(catalogue, "cards.markdown_card", "Vehicle", alias_id,
                    [data_key("active", "active", ACCENT, key_type="attribute"),
                     data_key("speed", "speed", BRAND),
                     data_key("fuel", "fuel", WARNING_COLOR),
                     data_key("latitude", "latitude", BRAND),
                     data_key("longitude", "longitude", BRAND)],
                    (24, 3), show_title=False)
    w["config"]["settings"] = {
        "useMarkdownTextFunction": True,
        "applyDefaultMarkdownStyle": False,
        "markdownTextPattern": "",
        "markdownTextFunction": f"""
var d = (data && data[0]) || {{}};
var label = d['entityLabel'] || d['entityName'] || 'Vehicle';
var name  = d['entityName'] || '';
var online = (d['active'] === true || d['active'] === 'true');
var speed = Number(d['speed']);
var fuel  = Number(d['fuel']);
var lat   = Number(d['latitude']);
var lon   = Number(d['longitude']);

function pill(text, bg, fg) {{
  return '<span class="bt-pill" style="background:' + bg + ';color:' + fg + '">' + text + '</span>';
}}

var pills = online ? pill('ONLINE', '#D1FAE5', '#047857')
                   : pill('OFFLINE', '#EDEAE4', '{MUTED}');
if (isFinite(speed) && speed > {SPEED_LIMIT:.0f}) {{
  pills += pill('OVERSPEED', '#FEE2E2', '{CRITICAL_COLOR}');
}}
if (isFinite(fuel) && fuel < {FUEL_LIMIT:.0f}) {{
  pills += pill('LOW FUEL', '#FEF3C7', '{WARNING_COLOR}');
}}

var where = '';
if (isFinite(lon)) {{
  if (lon < 67.09)       {{ where = 'Shahrah-e-Faisal &middot; West'; }}
  else if (lon < 67.131) {{ where = 'Shahrah-e-Faisal &middot; Central'; }}
  else if (lon < 67.141) {{ where = 'Natha Khan Bridge'; }}
  else if (lon < 67.160) {{ where = 'Shahrah-e-Faisal (Drigh Road)'; }}
  else                   {{ where = 'Shahrah-e-Faisal &middot; East'; }}
}}
var coords = (isFinite(lat) && isFinite(lon))
  ? lat.toFixed(5) + ', ' + lon.toFixed(5) : '&mdash;';

return '<div class="bt-vh">'
     + '<div class="bt-vh-l">'
     +   '<div class="bt-vh-id">' + label + '</div>'
     +   '<div class="bt-vh-name">' + name + '</div>'
     + '</div>'
     + '<div class="bt-vh-c">' + pills + '</div>'
     + '<div class="bt-vh-r">'
     +   '<div class="bt-vh-where">' + (where ? 'Karachi &middot; ' + where : 'Karachi') + '</div>'
     +   '<div class="bt-vh-coords">' + coords + '</div>'
     + '</div>'
     + '</div>';
""",
        "markdownCss": (
            ".bt-vh{display:flex;align-items:center;justify-content:space-between;"
            "gap:16px;height:100%;padding:4px 6px}"
            ".bt-vh-l{display:flex;flex-direction:column;gap:3px;"
            "border-left:4px solid " + ACCENT + ";padding-left:14px}"
            ".bt-vh-id{font:700 22px/1.1 Roboto,sans-serif;letter-spacing:.06em;"
            "color:" + BRAND + "}"
            ".bt-vh-name{font:400 12px/1.2 Roboto,sans-serif;color:" + MUTED + "}"
            ".bt-vh-c{display:flex;gap:8px;flex-wrap:wrap}"
            ".bt-pill{display:inline-block;padding:3px 11px;border-radius:999px;"
            "font:700 10px/1.6 Roboto,sans-serif;letter-spacing:.06em}"
            ".bt-vh-r{text-align:right}"
            ".bt-vh-where{font:600 12px/1.3 Roboto,sans-serif;color:" + BRAND + "}"
            ".bt-vh-coords{font:400 11px/1.3 Roboto,sans-serif;color:" + MUTED + "}"
        ),
    }
    style_widget(w["config"])
    return w

def build_vehicle_details(catalogue, alias_id):
    """Widgets and layout for the per-vehicle state."""
    widgets, layout = {}, {}

    def place(widget, col, row, size=None):
        if size:
            widget["sizeX"], widget["sizeY"] = size
        widgets[widget["id"]] = widget
        layout[widget["id"]] = {"sizeX": widget["sizeX"], "sizeY": widget["sizeY"],
                                "row": row, "col": col}

    place(vehicle_identity_header(catalogue, alias_id), 0, 0)

    # Circular instruments rather than number tiles. These reuse gauge_widget()
    # and the battery_level configuration already written for the Vehicle
    # Tracking Dashboard, so the two pages read as the same product and the
    # threshold bands are defined in exactly one place.
    #
    # A gauge belongs here and not on the Command Center: this state resolves to
    # one vehicle, whereas the fleet view holds three and a single dial could
    # not say which one it meant.
    place(gauge_widget(
        catalogue, "analogue_gauges.speed_gauge_canvas_gauges", alias_id,
        "speed", "Speed", "km/h", 0, 140,
        [{"from": 0, "to": SPEED_LIMIT, "color": ACCENT},
         {"from": SPEED_LIMIT, "to": 140, "color": CRITICAL_COLOR}],
        (6, 6), "Speed", "speed"), 0, 3)

    place(gauge_widget(
        catalogue, "analogue_gauges.radial_gauge_canvas_gauges", alias_id,
        "fuel", "Fuel", "%", 0, 100,
        [{"from": 0, "to": FUEL_LIMIT, "color": WARNING_COLOR},
         {"from": FUEL_LIMIT, "to": 100, "color": ACCENT}],
        (6, 6), "Fuel level", "local_gas_station"), 6, 3)

    battery_colour = color_fn(
        f"if (value < 20) {{ return '{CRITICAL_COLOR}'; }}\n"
        f"return '{BRAND}';", BRAND)
    battery = make_widget(
        catalogue, "battery_level", "Battery", alias_id,
        [data_key("battery", "Battery", ACCENT, units="%", decimals=0)],
        (5, 6), title_icon="battery_full")
    battery["config"]["settings"].update({
        "layout": "vertical_solid",
        "showValue": True,
        "autoScaleValueSize": True,
        "valueFont": font(24, "600"),
        "valueColor": color_const(BRAND),
        "batteryLevelColor": battery_colour,
        "batteryShapeColor": color_const(MUTED),
        "sectionsCount": 6,
    })
    battery["sizeX"], battery["sizeY"] = 4, 6
    place(battery, 12, 3)

    place(gauge_widget(
        catalogue, "analogue_gauges.temperature_radial_gauge_canvas_gauges", alias_id,
        "temperature", "Temp", "°C", 0, 60,
        [{"from": 0, "to": 40, "color": ACCENT},
         {"from": 40, "to": 60, "color": WARNING_COLOR}],
        (4, 6), "Temperature", "thermostat"), 16, 3)

    # Ignition stays a card: it is a two-state reading, and a dial with two
    # positions communicates less than the word does.
    ignition = metric_card(
        catalogue, "cards.value_card", alias_id, "ignition", "Ignition",
        "power_settings_new", None, 0,
        color_fn("return value === 'ON' ? '" + ACCENT + "' : '" + MUTED + "';", BRAND),
        color_fn("return value === 'ON' ? '" + ACCENT + "' : '" + MUTED + "';", MUTED))
    ig_key = ignition["config"]["datasources"][0]["dataKeys"][0]
    ig_key["usePostProcessing"] = True
    ig_key["postFuncBody"] = "return value ? 'ON' : 'OFF';"
    ignition["config"]["showTitle"] = True
    ignition["config"]["title"] = "Ignition"
    ignition["config"]["settings"]["valueFont"] = font(34, "700")
    place(ignition, 20, 3, (4, 6))

    vehicle_map = build_map(catalogue, "map", alias_id)
    vehicle_map["config"]["title"] = "Live location"
    vehicle_map["config"]["settings"]["markers"][0]["label"] = {
        "show": True, "type": "pattern", "pattern": "${entityLabel}"}
    place(vehicle_map, 0, 9, (15, 11))

    status = make_widget(
        catalogue, "cards.attributes_card", "Vehicle status", alias_id,
        [data_key("active", "Connectivity", ACCENT, key_type="attribute"),
         data_key("ignition", "Ignition", BRAND),
         data_key("speed", "Speed", BRAND, units="km/h", decimals=1),
         data_key("fuel", "Fuel", WARNING_COLOR, units="%", decimals=1),
         data_key("battery", "Battery", BRAND, units="%", decimals=0),
         data_key("temperature", "Temperature", BRAND, units="°C", decimals=1),
         data_key("heading", "Heading", BRAND, units="°", decimals=0),
         data_key("odometer", "Odometer", BRAND, units="km", decimals=1),
         data_key("latitude", "Latitude", MUTED, decimals=5),
         data_key("longitude", "Longitude", MUTED, decimals=5)],
        (9, 11), title_icon="fact_check")
    place(status, 15, 9)

    place(history_chart(
        catalogue, alias_id, "Speed and fuel · last 30 minutes", "show_chart",
        [data_key("speed", "Speed (km/h)", BRAND, units="km/h", decimals=1),
         data_key("fuel", "Fuel (%)", WARNING_COLOR, units="%", decimals=1)]),
        0, 20)

    place(history_chart(
        catalogue, alias_id, "Battery and temperature · last 30 minutes", "battery_charging_full",
        [data_key("battery", "Battery (%)", ACCENT, units="%", decimals=0),
         data_key("temperature", "Temperature (°C)", CRITICAL_COLOR, units="°C", decimals=1)]),
        0, 27, (24, 6))

    alerts = make_widget(catalogue, "alarm_widgets.alarms_table",
                         "Recent alerts for this vehicle", alias_id, [], (24, 6),
                         title_icon="warning")
    alerts["config"].pop("datasources", None)
    src = alerts["config"]["alarmSource"]
    src["type"] = "entity"
    src["entityAliasId"] = alias_id
    src["filterId"] = None
    alerts["config"]["alarmFilterConfig"] = {
        "statusList": ["ACTIVE", "CLEARED"], "severityList": [], "typeList": [],
        "searchPropagatedAlarms": False, "assignedToCurrentUser": False, "assigneeId": None}
    alerts["config"]["settings"].update({
        "enableSearch": False, "enableFilter": False, "displayDetails": True,
        "allowAcknowledgment": True, "allowClear": True, "displayActivity": False,
        "displayPagination": True, "defaultPageSize": 6,
        "enableSelectColumnDisplay": False, "defaultSortOrder": "-createdTime"})
    place(alerts, 0, 33)

    return widgets, layout

def build_fleet_overview(catalogue):
    all_id = str(uuid.uuid4())
    vehicle_alias_id = str(uuid.uuid4())
    online_filter_id, offline_filter_id = str(uuid.uuid4()), str(uuid.uuid4())
    widgets, layout = {}, {}

    def place(widget, col, row):
        widgets[widget["id"]] = widget
        layout[widget["id"]] = {"sizeX": widget["sizeX"], "sizeY": widget["sizeY"],
                                "row": row, "col": col}

    place(command_centre_header(catalogue, all_id), 0, 0)

    # --- KPI row ---------------------------------------------------------
    place(count_tile(catalogue, all_id, "Total vehicles", "local_shipping", BRAND,
                     wave=ACCENT), 0, 3)
    place(count_tile(catalogue, all_id, "Online", "wifi", ACCENT,
                     filter_id=online_filter_id, wave=ACCENT), 6, 3)
    place(count_tile(catalogue, all_id, "Offline", "wifi_off", MUTED,
                     filter_id=offline_filter_id, wave=MUTED), 12, 3)

    alerts_tile = make_widget(catalogue, "alarm_count", "Active alerts", all_id, [], (6, 3),
                              title_icon="notifications_active", show_title=False)
    alerts_tile["config"]["datasources"] = [{
        "type": "alarmCount", "name": None, "entityAliasId": all_id, "filterId": None,
        "dataKeys": [{"name": "count", "type": "count", "label": "Active alerts",
                      "color": CRITICAL_COLOR, "settings": {}, "_hash": random.random()}],
        "alarmFilterConfig": {"statusList": ["ACTIVE"], "severityList": [], "typeList": [],
                              "searchPropagatedAlarms": False,
                              "assignedToCurrentUser": False, "assigneeId": None},
    }]
    alerts_tile["config"]["settings"].update({
        "showLabel": True, "label": "Active alerts",
        "labelFont": font(13, "500"), "labelColor": color_const(MUTED),
        "showIcon": True, "icon": "notifications_active", "iconSize": 28,
        "iconSizeUnit": "px",
        "iconColor": color_fn(f"return value > 0 ? '{CRITICAL_COLOR}' : '{ACCENT}';", ACCENT),
        "showIconBackground": True, "iconBackgroundSize": 46, "iconBackgroundSizeUnit": "px",
        "iconBackgroundColor": color_const("#e6f1ec"),
        "valueFont": font(38, "600"),
        "valueColor": color_fn(f"return value > 0 ? '{CRITICAL_COLOR}' : '{BRAND}';", BRAND),
        "layout": "horizontal",
    })
    alerts_tile["config"]["widgetCss"] = kpi_wave_css(CRITICAL_COLOR)
    alerts_tile["config"]["padding"] = "10px 10px 26px"
    place(alerts_tile, 18, 3)

    # --- Live fleet map --------------------------------------------------
    fleet_map = build_map(catalogue, "map", all_id)
    fleet_map["config"]["title"] = "Live fleet tracking"
    fleet_map["sizeX"], fleet_map["sizeY"] = 15, 13
    marker = fleet_map["config"]["settings"]["markers"][0]
    marker["dsLabel"] = "Fleet"
    marker["label"] = {"show": True, "type": "pattern", "pattern": "${entityLabel}"}
    marker["tooltip"] = {
        "show": True, "trigger": "hover", "autoclose": False, "type": "pattern",
        "pattern": (
            '<div style="font:700 13px Roboto;color:' + BRAND + '">${entityLabel}</div>'
            '<div style="font:400 12px Roboto;color:' + MUTED + ';margin-top:4px">'
            'Speed <b>${speed:1} km/h</b><br/>'
            'Fuel <b>${fuel:1} %</b><br/>'
            'Battery <b>${battery:1} %</b><br/>'
            'Ignition <b>${ignition}</b></div>'),
    }
    fleet_map["config"]["actions"] = {"markerClick": open_details_action()}
    place(fleet_map, 0, 6)

    # --- Fleet vehicles --------------------------------------------------
    # Speed and fuel render as compact radials from the live reading, matching
    # the fleet-console reference. The number stays inside the ring so the value
    # is never separated from the visual.
    speed_content = PILL_JS + DONUT_JS + f"""
var v = Number(value);
if (!isFinite(v)) {{ return '&mdash;'; }}
var over = v > {SPEED_LIMIT:.0f};
var colour = over ? '{CRITICAL_COLOR}' : '{BRAND}';
return donut(v, 140, colour, v.toFixed(0), 'km/h');
"""

    fuel_content = PILL_JS + DONUT_JS + f"""
var v = Number(value);
if (!isFinite(v)) {{ return '&mdash;'; }}
var low = v < {FUEL_LIMIT:.0f};
var colour = low ? '{WARNING_COLOR}' : '{ACCENT}';
return donut(v, 100, colour, v.toFixed(0) + '%', '');
"""

    status_content = PILL_JS + f"""
var online = (value === true || value === 'true');
return online ? pill('ONLINE', '#D1FAE5', '#047857')
              : pill('OFFLINE', '#EDEAE4', '{MUTED}');
"""

    # Name over profile, as the reference shows: the fleet id is what an
    # operator reads, the tracker type is context underneath it.
    vehicle_content = f"""
return '<div style="line-height:1.35">'
     + '<div style="font:700 13px Roboto,sans-serif;letter-spacing:.03em;color:{BRAND}">'
     +   (value || '') + '</div>'
     + '<div style="font:400 11px Roboto,sans-serif;color:{MUTED}">GPS Tracker</div>'
     + '</div>';
"""

    table = make_widget(catalogue, "cards.entities_table", "Fleet vehicles", all_id, [],
                        (9, 13), title_icon="local_shipping")

    def col(name, key_type, label, content_js, width="0px"):
        k = {"name": name, "type": key_type, "label": label, "color": BRAND,
             "_hash": random.random(),
             "settings": {"columnWidth": width,
                          "useCellStyleFunction": False, "cellStyleFunction": "",
                          "useCellContentFunction": True,
                          "cellContentFunction": content_js}}
        return k

    table["config"]["datasources"] = [{
        "type": "entity", "name": None, "entityAliasId": all_id, "filterId": None,
        "dataKeys": [
            col("label", "entityField", "Vehicle", vehicle_content, "110px"),
            col("active", "attribute", "Status", status_content, "110px"),
            col("speed", "timeseries", "Speed", speed_content, "150px"),
            col("fuel", "timeseries", "Fuel", fuel_content, "130px"),
            col("longitude", "timeseries", "Location", LOCATION_JS),
        ],
    }]
    table["config"]["settings"].update({
        "enableSearch": False, "displayPagination": False,
        "displayEntityName": False, "displayEntityLabel": False,
        "displayEntityType": False, "enableStickyHeader": True,
        "enableSelectColumnDisplay": False, "entitiesTitle": "Vehicles",
    })
    table["config"]["actions"] = {"rowClick": open_details_action()}
    place(table, 15, 6)

    # --- Active alerts ---------------------------------------------------
    # Icon plus badge, as on the reference console. HTML entities rather than
    # literal emoji so the payload stays ASCII through provisioning.
    alert_type_content = PILL_JS + f"""
var t = String(value || '');
function row(icon, text, bg, fg) {{
  return '<span style="display:inline-flex;align-items:center;gap:7px">'
       + '<span style="font-size:14px;line-height:1">' + icon + '</span>'
       + pill(text, bg, fg) + '</span>';
}}
if (t.indexOf('Overspeed') >= 0) {{ return row('&#9201;',   'OVERSPEED', '#FEE2E2', '{CRITICAL_COLOR}'); }}
if (t.indexOf('Low Fuel')  >= 0) {{ return row('&#9981;',   'LOW FUEL',  '#FEF3C7', '{WARNING_COLOR}'); }}
if (t.indexOf('Offline')   >= 0) {{ return row('&#128246;', 'OFFLINE',   '#EDEAE4', '{MUTED}'); }}
return t;
"""

    alert_vehicle_content = f"""
var name = String(value || '');
return '<span style="font:700 12px Roboto,sans-serif;letter-spacing:.03em;color:{BRAND}">'
     + name + '</span>';
"""

    alert_time_content = f"""
return '<span style="font:500 12px Roboto,sans-serif;color:{BRAND}">' + (value || '') + '</span>';
"""

    # ACTIVE reads red, anything cleared reads quiet: an operator scanning this
    # table only needs to pick out what is still live.
    alert_status_content = PILL_JS + f"""
var st = String(value || '');
if (st.indexOf('ACTIVE') >= 0) {{ return pill('ACTIVE', '#FEE2E2', '{CRITICAL_COLOR}'); }}
return pill('CLEARED', '#EDEAE4', '{MUTED}');
"""

    alerts = make_widget(catalogue, "alarm_widgets.alarms_table", "Active alerts",
                         all_id, [], (24, 7), title_icon="warning")
    alerts["config"].pop("datasources", None)
    src = alerts["config"]["alarmSource"]
    src["type"] = "entity"
    src["entityAliasId"] = all_id
    src["filterId"] = None

    def akey(name, label, content_js=None, width="0px"):
        return {"name": name, "type": "alarm", "label": label, "color": BRAND,
                "_hash": random.random(),
                "settings": {"columnWidth": width,
                             "useCellStyleFunction": False, "cellStyleFunction": "",
                             "useCellContentFunction": bool(content_js),
                             "cellContentFunction": content_js or ""}}

    # The stock column set is Created time / Originator / Type / Severity /
    # Status / Assignee, which is the platform's vocabulary. A fleet operator
    # wants to know which vehicle, what happened, and whether it is still live.
    src["dataKeys"] = [
        akey("createdTime", "Time", alert_time_content, "160px"),
        akey("originatorLabel", "Vehicle", alert_vehicle_content, "140px"),
        akey("type", "Alert", alert_type_content, "170px"),
        akey("details", "Detail"),
        akey("status", "Status", alert_status_content, "130px"),
    ]
    alerts["config"]["alarmFilterConfig"] = {
        "statusList": ["ACTIVE", "CLEARED"], "severityList": [], "typeList": [],
        "searchPropagatedAlarms": False, "assignedToCurrentUser": False, "assigneeId": None}
    alerts["config"]["settings"].update({
        "enableSearch": False, "enableFilter": False, "displayDetails": True,
        "allowAcknowledgment": True, "allowClear": True, "displayActivity": False,
        "displayPagination": True, "defaultPageSize": 8,
        "enableSelectColumnDisplay": False,
        "defaultSortOrder": "-createdTime"})
    place(alerts, 0, 19)

    # The per-vehicle state lives in the same dashboard so the entity state
    # controller can push it onto its stack - that stack is what gives the
    # breadcrumb and the way back to the fleet, with nothing to implement.
    detail_widgets, detail_layout = build_vehicle_details(catalogue, vehicle_alias_id)
    widgets.update(detail_widgets)

    grid = {"backgroundColor": CANVAS, "columns": 24, "margin": 10,
            "outerMargin": True, "backgroundSizeMode": "100%",
            "autoFillHeight": False, "mobileAutoFillHeight": False,
            "mobileRowHeight": 70}

    return {
        "title": FLEET_DASHBOARD_TITLE,
        "configuration": {
            "description": "Fleet command centre for Demo Logistics Company.",
            "widgets": widgets,
            "states": {
                "default": {"name": FLEET_DASHBOARD_TITLE, "root": True,
                            "layouts": {"main": {"widgets": layout,
                                                 "gridSettings": dict(grid)}}},
                VEHICLE_STATE_ID: {"name": "Vehicle", "root": False,
                                   "layouts": {"main": {"widgets": detail_layout,
                                                        "gridSettings": dict(grid)}}},
            },
            "entityAliases": {
                all_id: fleet_alias(all_id, "Fleet"),
                vehicle_alias_id: state_entity_alias(vehicle_alias_id),
            },
            "filters": {
                online_filter_id: status_filter(online_filter_id, "Online", True),
                offline_filter_id: status_filter(offline_filter_id, "Offline", False),
            },
            # Every widget here reads latest values or alarms, so there is no
            # historical aggregation running behind the page.
            "timewindow": {"displayValue": "", "selectedTab": 0,
                           "realtime": {"interval": 5000, "timewindowMs": 300000},
                           "aggregation": {"type": "NONE", "limit": 5000}},
            "settings": {"stateControllerId": "entity", "showTitle": False,
                         "showDashboardsSelect": False, "showEntitiesSelect": False,
                         "showDashboardTimewindow": False, "showDashboardExport": False,
                         "showFilters": False, "toolbarAlwaysOpen": False},
        },
    }
