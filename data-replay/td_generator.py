"""Generate W3C WoT Thing Descriptions from sources.yaml device entries.

Each generated TD points its hrefs at the replay server's base URL.
"""

import uuid

# Stable namespace UUID for deterministic TD id generation from device IDs
_NAMESPACE = uuid.UUID("e8f5a3b1-7c2d-4f9e-b6a1-d3e8f5a3b17c")

URI_VARIABLES = {
    "from": {
        "type": "integer",
        "description": "Start time (Unix timestamp in milliseconds) for the history data",
    },
    "to": {
        "type": "integer",
        "description": "End time (Unix timestamp in milliseconds) for the history data",
    },
}

THERMOSTAT_DATA10_SCHEMA = {
    "type": "object",
    "encoded": "swsb-data10",
    "description": "Thermostat state data",
    "properties": {
        "battery_voltage": {
            "type": "object",
            "description": "Battery voltage level",
            "properties": {
                "value": {"type": "string"},
                "unit": {"type": "string", "const": "mV"},
            },
        },
        "heating_control": {
            "type": "object",
            "description": "Heating control parameters and status",
            "properties": {
                "room_temperature": {
                    "type": "object",
                    "description": "Current room temperature",
                    "properties": {
                        "value": {"type": "string"},
                        "unit": {"type": "string", "const": "°C"},
                    },
                },
                "set_point_temperature": {
                    "type": "object",
                    "description": "Target temperature setpoint",
                    "properties": {
                        "value": {"type": "string"},
                        "unit": {"type": "string", "const": "°C"},
                    },
                },
                "valve_position": {
                    "type": "object",
                    "description": "Current valve opening position",
                    "properties": {
                        "value": {"type": "string"},
                        "unit": {"type": "string", "const": "%"},
                    },
                },
                "gain": {
                    "type": "object",
                    "description": "PI controller gain parameters",
                    "properties": {
                        "p": {
                            "type": "object",
                            "properties": {"value": {"type": "number"}},
                        },
                        "i": {
                            "type": "object",
                            "properties": {"value": {"type": "number"}},
                        },
                        "unit": {"type": "string", "const": "uint"},
                    },
                },
                "mode": {
                    "type": "object",
                    "description": "Operating mode settings",
                    "properties": {
                        "holiday": {
                            "type": "object",
                            "properties": {
                                "is_pending": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "boolean"},
                                        "unit": {"type": "string", "const": "bool"},
                                    },
                                }
                            },
                        },
                        "window_open_detection": {
                            "type": "object",
                            "properties": {
                                "is_open": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "boolean"},
                                        "unit": {"type": "string", "const": "bool"},
                                    },
                                }
                            },
                        },
                        "active_mode": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                                "unit": {"type": "string", "const": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}

MULTISENSOR_PROPERTIES = {
    "Temperature": {
        "key": "temperature",
        "desc": "Current room temperature reading",
        "history_desc": "Retrieve historical temperature readings for a given time range",
        "unit": "°C",
        "value_type": "number",
    },
    "CO2": {
        "key": "co2",
        "desc": "Current CO2 concentration level (air quality indicator)",
        "history_desc": "Retrieve historical CO2 readings for a given time range",
        "unit": "ppm",
        "value_type": "number",
    },
    "Humidity": {
        "key": "humidity",
        "desc": "Current relative humidity level",
        "history_desc": "Retrieve historical humidity readings for a given time range",
        "unit": "%",
        "value_type": "number",
    },
    "Light": {
        "key": "light",
        "desc": "Current ambient light level (illuminance)",
        "history_desc": "Retrieve historical light level readings for a given time range",
        "unit": "lx",
        "value_type": "number",
    },
    "Motion": {
        "key": "motion",
        "desc": "Motion detection count within the sampling interval (presence/activity indicator)",
        "history_desc": "Retrieve historical motion detection counts for a given time range",
        "unit": "count per interval",
        "value_type": "integer",
    },
}


def _td_id(device_id: str) -> str:
    return f"urn:uuid:{uuid.uuid5(_NAMESPACE, device_id)}"


def _base_td(device: dict) -> dict:
    td = {
        "@context": "https://www.w3.org/2022/wot/td/v1.1",
        "id": _td_id(device["id"]),
        "@type": "Thing",
        "title": device["title"],
        "description": device["description"],
        "location": device["location"],
        "security": "nosec_sc",
        "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}},
    }
    metadata = device.get("metadata")
    if metadata is not None:
        td["metadata"] = metadata
    return td


def generate_smart_meter_td(device: dict, replay_base_url: str) -> dict:
    device_id = device["id"]
    server_base = replay_base_url.rstrip("/")
    td = _base_td(device)
    td["properties"] = {
        "power": {
            "description": "Current power consumption reading",
            "type": "object",
            "unit": "W",
            "readOnly": True,
            "forms": [
                {
                    "op": ["readproperty"],
                    "href": f"{server_base}/api/history/{device_id}/power/latest?includeTimestamps=true",
                    "contentType": "application/json",
                }
            ],
            "properties": {
                "ts": {
                    "type": "integer",
                    "description": "Unix timestamp in milliseconds",
                },
                "power": {"type": "number", "unit": "W"},
            },
        }
    }
    td["actions"] = {
        "get_power_history": {
            "description": "Retrieve historical power consumption readings for a given time range",
            "safe": True,
            "idempotent": True,
            "unit": "W",
            "forms": [
                {
                    "op": "invokeaction",
                    "href": f"{server_base}/api/history/{device_id}/power{{?from,to}}",
                    "contentType": "application/json",
                    "htv:methodName": "GET",
                }
            ],
            "output": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ts": {
                            "type": "integer",
                            "description": "Unix timestamp in milliseconds",
                        },
                        "power": {"type": "number", "unit": "W"},
                    },
                },
            },
            "uriVariables": URI_VARIABLES,
        }
    }
    return td


def generate_multisensor_td(device: dict, replay_base_url: str) -> dict:
    device_id = device["id"]
    server_base = replay_base_url.rstrip("/")
    td = _base_td(device)

    td_properties = {}
    td_actions = {}

    for api_prop in device["properties"]:
        meta = MULTISENSOR_PROPERTIES[api_prop]
        key = meta["key"]

        td_properties[key] = {
            "description": meta["desc"],
            "type": "object",
            "unit": meta["unit"],
            "readOnly": True,
            "forms": [
                {
                    "op": ["readproperty"],
                    "href": f"{server_base}/api/history/{device_id}/{api_prop}/latest?includeTimestamps=true",
                    "contentType": "application/json",
                }
            ],
            "properties": {
                "ts": {
                    "type": "integer",
                    "description": "Unix timestamp in milliseconds",
                },
                "value": {"type": meta["value_type"], "unit": meta["unit"]},
            },
        }

        action_name = f"get_{key}_history"
        td_actions[action_name] = {
            "description": meta["history_desc"],
            "safe": True,
            "idempotent": True,
            "unit": meta["unit"],
            "forms": [
                {
                    "op": "invokeaction",
                    "href": f"{server_base}/api/history/{device_id}/{api_prop}{{?from,to}}",
                    "contentType": "application/json",
                    "htv:methodName": "GET",
                }
            ],
            "output": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ts": {
                            "type": "integer",
                            "description": "Unix timestamp in milliseconds",
                        },
                        api_prop: {"type": meta["value_type"], "unit": meta["unit"]},
                    },
                },
            },
            "uriVariables": URI_VARIABLES,
        }

    td["properties"] = td_properties
    td["actions"] = td_actions
    return td


def generate_thermostat_td(device: dict, replay_base_url: str) -> dict:
    device_id = device["id"]
    server_base = replay_base_url.rstrip("/")
    td = _base_td(device)
    td["properties"] = {
        "state": {
            "description": "Current thermostat state including battery, heating control, temperatures, valve position, and operating modes",
            "type": "object",
            "readOnly": True,
            "forms": [
                {
                    "op": ["readproperty"],
                    "href": f"{server_base}/api/history/{device_id}/DATA%2010/latest?includeTimestamps=true",
                    "contentType": "application/json",
                }
            ],
            "properties": {
                "ts": {
                    "type": "integer",
                    "description": "Unix timestamp in milliseconds",
                },
                "DATA 10": THERMOSTAT_DATA10_SCHEMA,
            },
        }
    }
    td["actions"] = {
        "get_state_history": {
            "description": "Retrieve historical thermostat state data for a given time range",
            "safe": True,
            "idempotent": True,
            "forms": [
                {
                    "op": "invokeaction",
                    "href": f"{server_base}/api/history/{device_id}/DATA%2010{{?from,to}}",
                    "contentType": "application/json",
                    "htv:methodName": "GET",
                }
            ],
            "output": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ts": {
                            "type": "integer",
                            "description": "Unix timestamp in milliseconds",
                        },
                        "DATA 10": THERMOSTAT_DATA10_SCHEMA,
                    },
                },
            },
            "uriVariables": URI_VARIABLES,
        }
    }
    return td


_GENERATORS = {
    "smart_meter": generate_smart_meter_td,
    "multisensor": generate_multisensor_td,
    "thermostat": generate_thermostat_td,
}


def generate_td(device: dict, replay_base_url: str) -> dict:
    """Generate a WoT Thing Description for a device entry from sources.yaml."""
    device_type = device["type"]
    generator = _GENERATORS.get(device_type)
    if generator is None:
        raise ValueError(f"Unknown device type: {device_type}")
    return generator(device, replay_base_url)
