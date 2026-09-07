"""Constants pour Smart Wind Cover."""

DOMAIN = "smart_wind_cover"

# Entités
CONF_PHYSICAL_COVER = "physical_cover"
CONF_WIND_SENSOR = "wind_sensor"

# Groupes KNX optionnels
CONF_MOVE_GA = "move_ga"
CONF_STOP_GA = "stop_ga"

# Temporisation et paliers
CONF_DELAY_OFF = "delay_off"
DEFAULT_DELAY_OFF = 30

CONF_WIND_RULES = "wind_rules"
DEFAULT_WIND_RULES = "5:25, 10:50, 15:75, 20:100"  # Vent:PositionMin (%)