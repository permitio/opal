import unittest
from opal_common.config import opal_common_config
from opal_client.config import opal_client_config
from opal_server.config import opal_server_config

class TestConfigDescriptions(unittest.TestCase):
    def test_opal_common_config_descriptions(self):
        for name, entry in opal_common_config.entries.items():
            with self.subTest(name=name):
                self.assertIsNotNone(entry.description, f"{name} is missing a description")

    def test_opal_client_config_descriptions(self):
        for name, entry in opal_client_config.entries.items():
            with self.subTest(name=name):
                self.assertIsNotNone(entry.description, f"{name} is missing a description")

    def test_opal_server_config_descriptions(self):
        for name, entry in opal_server_config.entries.items():
            with self.subTest(name=name):
                self.assertIsNotNone(entry.description, f"{name} is missing a description")

if __name__ == "__main__":
    unittest.main()
