import unittest

import td_generator


REPLAY_BASE_URL = "https://replay.example.test"


class TdGeneratorTestCase(unittest.TestCase):
    def test_smart_meter_td_includes_metadata_and_history_contract(self) -> None:
        device = {
            "id": "wYDLYqAj21FIAoMm2zUz",
            "type": "smart_meter",
            "title": "Smart Meter House 5",
            "description": "Smart electricity meter measuring power consumption for a residential household",
            "location": {"building": "REFIT", "house": "5"},
            "metadata": {
                "device_id": "wYDLYqAj21FIAoMm2zUz",
                "manufacturer": "Unknown",
                "model": "Smart Meter",
                "dataset": "REFIT Electrical Load Measurements",
            },
            "properties": ["power"],
        }

        td = td_generator.generate_td(device, REPLAY_BASE_URL)

        self.assertEqual(td["metadata"], device["metadata"])
        self.assertEqual(td["properties"]["power"]["unit"], "W")
        self.assertEqual(
            td["properties"]["power"]["forms"][0]["href"],
            f"{REPLAY_BASE_URL}/api/history/{device['id']}/power/latest?includeTimestamps=true",
        )
        self.assertEqual(
            td["actions"]["get_power_history"]["description"],
            "Retrieve historical power consumption readings for a given time range",
        )

    def test_multisensor_td_preserves_metadata_and_original_action_wording(
        self,
    ) -> None:
        device = {
            "id": "5u7xysVleBeim3fcamZf",
            "type": "multisensor",
            "title": "Kitchen Multisensor",
            "description": "Environmental multisensor monitoring temperature, humidity, CO2, light, and motion in the kitchen",
            "location": {
                "building": "Dudopark",
                "apartment": "1",
                "room": "Kitchen",
            },
            "metadata": {
                "device_id": "A81758FFFE0528A8",
                "manufacturer": "Unknown",
                "model": "Multisensor",
                "firmware_version": "1.0.0",
                "installation_date": "2024-01-01",
            },
            "properties": ["Temperature", "CO2", "Humidity", "Light", "Motion"],
        }

        td = td_generator.generate_td(device, REPLAY_BASE_URL)

        self.assertEqual(td["metadata"], device["metadata"])
        self.assertEqual(
            td["actions"]["get_temperature_history"]["description"],
            "Retrieve historical temperature readings for a given time range",
        )
        self.assertEqual(
            td["actions"]["get_co2_history"]["description"],
            "Retrieve historical CO2 readings for a given time range",
        )
        self.assertEqual(
            td["actions"]["get_light_history"]["description"],
            "Retrieve historical light level readings for a given time range",
        )
        self.assertEqual(
            td["actions"]["get_motion_history"]["description"],
            "Retrieve historical motion detection counts for a given time range",
        )
        self.assertEqual(td["properties"]["co2"]["unit"], "ppm")
        self.assertEqual(
            td["properties"]["motion"]["properties"]["value"]["type"], "integer"
        )

    def test_thermostat_td_includes_metadata_and_state_schema(self) -> None:
        device = {
            "id": "Kj8hViu74Ewjrp1PH26G",
            "type": "thermostat",
            "title": "Living Room Left Thermostat",
            "description": "Smart thermostat controlling heating in the Living Room (Left) with temperature setpoint, valve position, and various operating modes",
            "location": {
                "building": "Dudopark",
                "apartment": "1",
                "room": "Living Room",
            },
            "metadata": {
                "device_id": "Kj8hViu74Ewjrp1PH26G",
                "manufacturer": "Unknown",
                "model": "Thermostat",
                "firmware_version": "1.0.0",
                "installation_date": "2024-01-01",
            },
            "properties": ["DATA%2010"],
        }

        td = td_generator.generate_td(device, REPLAY_BASE_URL)

        self.assertEqual(td["metadata"], device["metadata"])
        self.assertEqual(td["properties"]["state"]["readOnly"], True)
        self.assertEqual(
            td["properties"]["state"]["properties"]["DATA 10"]["encoded"],
            "swsb-data10",
        )
        self.assertEqual(
            td["actions"]["get_state_history"]["forms"][0]["href"],
            f"{REPLAY_BASE_URL}/api/history/{device['id']}/DATA%2010{{?from,to}}",
        )


if __name__ == "__main__":
    unittest.main()
