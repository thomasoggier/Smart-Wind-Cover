import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

# Simulation simple pour exécuter le test sans Home Assistant
class TestStoreVent(unittest.TestCase):

    def setUp(self):
        # Configuration de simulation
        self.config = {
            "name": "Store Test",
            "wind_sensor": "input_number.vent_simulation",
            "feedback_sensor": "sensor.rez_terrasse_md_fb",
            "knx_position_address": "2/2/201",
            "delay_off_seconds": 300,
            "regles_vent": [
                {"vent": 5, "max": 75},
                {"vent": 10, "max": 50},
                {"vent": 20, "max": 0},
            ]
        }

    def test_calcul_limites_vent(self):
        """ Test du calcul de limite selon la vitesse du vent """
        # Tri des règles comme dans le composant réel
        regles = sorted(self.config["regles_vent"], key=lambda k: k["vent"])

        def get_max_allowed(wind_speed):
            applicable = [r["max"] for r in regles if r["vent"] <= wind_speed]
            return min(applicable) if applicable else 100

        # Vérifications
        self.assertEqual(get_max_allowed(2), 100)  # Vent faible -> 100%
        self.assertEqual(get_max_allowed(7), 75)   # Vent 7 km/h -> Max 75%
        self.assertEqual(get_max_allowed(12), 50)  # Vent 12 km/h -> Max 50%
        self.assertEqual(get_max_allowed(25), 0)   # Vent 25 km/h -> Repli complet (0%)

if __name__ == '__main__':
    unittest.main()