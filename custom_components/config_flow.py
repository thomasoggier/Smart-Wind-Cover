"""Config flow pour Smart Wind Cover."""
import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_PHYSICAL_COVER,
    CONF_WIND_SENSOR,
    CONF_MOVE_GA,
    CONF_STOP_GA,
    CONF_DELAY_OFF,
    DEFAULT_DELAY_OFF,
    CONF_WIND_RULES,
    DEFAULT_WIND_RULES,
)

_LOGGER = logging.getLogger(__name__)


class WindProtectedCoverConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère le Config Flow pour l'intégration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Étape initiale de configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            cover_entity = user_input[CONF_PHYSICAL_COVER]
            state = self.hass.states.get(cover_entity)
            title = state.name if state else cover_entity

            return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_PHYSICAL_COVER): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="cover")
            ),
            vol.Required(CONF_WIND_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_number"])
            ),
            vol.Optional(CONF_WIND_RULES, default=DEFAULT_WIND_RULES): str,
            vol.Optional(CONF_MOVE_GA): str,
            vol.Optional(CONF_STOP_GA): str,
            vol.Optional(CONF_DELAY_OFF, default=DEFAULT_DELAY_OFF): cv.positive_int,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Obtenir le gestionnaire d'options UI."""
        return WindProtectedCoverOptionsFlowHandler()


class WindProtectedCoverOptionsFlowHandler(config_entries.OptionsFlow):
    """Gère le menu d'options (roue dentée)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Formulaire de modification des options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        # Récupération des valeurs actuelles (priorité aux options, puis à data)
        current_rules = options.get(
            CONF_WIND_RULES, data.get(CONF_WIND_RULES, DEFAULT_WIND_RULES)
        )
        current_delay = options.get(
            CONF_DELAY_OFF, data.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF)
        )
        current_wind_sensor = options.get(
            CONF_WIND_SENSOR, data.get(CONF_WIND_SENSOR, "")
        )
        current_move_ga = options.get(
            CONF_MOVE_GA, data.get(CONF_MOVE_GA, "")
        )
        current_stop_ga = options.get(
            CONF_STOP_GA, data.get(CONF_STOP_GA, "")
        )

        schema = vol.Schema({
            vol.Optional(
                CONF_WIND_SENSOR, default=current_wind_sensor
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_number"])
            ),
            vol.Optional(CONF_WIND_RULES, default=current_rules): str,
            vol.Optional(CONF_DELAY_OFF, default=current_delay): cv.positive_int,
            vol.Optional(CONF_MOVE_GA, default=current_move_ga): str,
            vol.Optional(CONF_STOP_GA, default=current_stop_ga): str,
        })

        return self.async_show_form(step_id="init", data_schema=schema)