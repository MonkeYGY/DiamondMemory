import unittest

from app.api import system_routes


class CapabilitiesApiTests(unittest.TestCase):
    def test_capabilities_returns_allowed_flags(self):
        endpoint = getattr(system_routes, "get_capabilities", None)
        self.assertTrue(callable(endpoint), "get_capabilities should exist")
        data = endpoint()
        self.assertIn("backend_ready", data)
        self.assertIn("model_ready", data)
        self.assertIn("allowed", data)
        self.assertTrue(data["allowed"]["browse"])
        self.assertTrue(data["allowed"]["search"])


if __name__ == "__main__":
    unittest.main()
