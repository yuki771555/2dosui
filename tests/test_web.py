import tempfile
from pathlib import Path
import unittest

from twodosumi.config import AppConfig, Secrets, save_config, save_secrets


class WebTests(unittest.TestCase):
    def test_settings_requires_auth_and_can_update_config(self):
        from twodosumi.web import create_app

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            secrets_path = Path(tmp) / "secrets.json"
            save_config(config_path, AppConfig(reader="mock", log_path=str(Path(tmp) / "log.csv")))
            save_secrets(secrets_path, Secrets(web_ui_token="token"))

            try:
                app = create_app(str(config_path), str(secrets_path))
            except RuntimeError as exc:
                self.skipTest(str(exc))
            client = app.test_client()
            self.assertEqual(client.get("/api/settings").status_code, 401)

            res = client.post(
                "/api/settings",
                json={
                    "settings": {
                        "person_weight_kg": 70,
                        "alarm_enabled": True,
                        "buzzer_enabled": True,
                        "buzzer_pin": "D13",
                        "scheduled_alarm_enabled": True,
                        "bed_recheck_minutes": 5,
                        "wake_mission_enabled": True,
                        "wake_mission_required_off_bed_sec": 30,
                        "scheduled_alarms": [
                            {
                                "id": "morning",
                                "time": "07:00",
                                "enabled": True,
                                "label": "Wake up",
                                "weekdays": [0, 1, 2, 3, 4],
                            }
                        ],
                        "webhook_enabled": True,
                    }
                },
                headers={"X-2Dosumi-Token": "token"},
            )
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.get_json()["ok"])

            res = client.get("/api/settings", headers={"X-2Dosumi-Token": "token"})
            settings = res.get_json()["settings"]
            self.assertEqual(settings["person_weight_kg"], 70)
            self.assertTrue(settings["alarm_enabled"])
            self.assertTrue(settings["buzzer_enabled"])
            self.assertEqual(settings["buzzer_pin"], "D13")
            self.assertTrue(settings["scheduled_alarm_enabled"])
            self.assertEqual(settings["bed_recheck_minutes"], 5)
            self.assertTrue(settings["wake_mission_enabled"])
            self.assertEqual(settings["wake_mission_required_off_bed_sec"], 30)
            self.assertEqual(settings["scheduled_alarms"][0]["id"], "morning")
            self.assertEqual(settings["scheduled_alarms"][0]["time"], "07:00")
            self.assertEqual(settings["scheduled_alarms"][0]["weekdays"], [0, 1, 2, 3, 4])
            self.assertTrue(settings["webhook_enabled"])

            res = client.post(
                "/api/sensor/check",
                json={"samples": 3, "interval_sec": 0},
                headers={"X-2Dosumi-Token": "token"},
            )
            self.assertEqual(res.status_code, 200)
            body = res.get_json()
            self.assertTrue(body["ok"])
            self.assertTrue(body["sensor"]["ok"])
            self.assertEqual(body["sensor"]["samples_read"], 3)


if __name__ == "__main__":
    unittest.main()
