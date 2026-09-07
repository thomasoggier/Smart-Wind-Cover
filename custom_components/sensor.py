"""Plateforme Sensor pour l'intégration Smart Wind Cover."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configuration des capteurs d'attributs."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    cover_entity = entry_data.get("cover_entity")

    if not cover_entity:
        _LOGGER.warning(
            "Instance Cover non trouvée dans hass.data pour %s, report des sensors",
            entry.entry_id,
        )
        return

    sensors = [
        SmartCoverDirectSensor(
            entry=entry,
            cover_entity=cover_entity,
            attribute_key="user_consigne",
            name_suffix="Consigne Utilisateur",
            unique_id_suffix="user_consigne",
        ),
        SmartCoverDirectSensor(
            entry=entry,
            cover_entity=cover_entity,
            attribute_key="safety_limit",
            name_suffix="Limite Sécurité Vent",
            unique_id_suffix="safety_limit",
        ),
        SmartCoverDirectSensor(
            entry=entry,
            cover_entity=cover_entity,
            attribute_key="target_position",
            name_suffix="Position Cible",
            unique_id_suffix="target_position",
        ),
    ]

    async_add_entities(sensors)


class SmartCoverDirectSensor(SensorEntity):
    """Capteur lisant directement les valeurs de l'instance Cover."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        cover_entity: Any,
        attribute_key: str,
        name_suffix: str,
        unique_id_suffix: str,
    ) -> None:
        """Initialisation du capteur."""
        self._entry = entry
        self._cover = cover_entity
        self._attribute_key = attribute_key
        self._attr_name = name_suffix
        self._attr_unique_id = f"{entry.entry_id}_{unique_id_suffix}"

    @property
    def native_value(self) -> int | float | None:
        """Lecture directe sur la propriété extra_state_attributes du cover."""
        attrs = getattr(self._cover, "extra_state_attributes", {})
        val = attrs.get(self._attribute_key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                return val
        return None

    async def async_added_to_hass(self) -> None:
        """S'abonne aux mises à jour d'état."""
        await super().async_added_to_hass()

        @callback
        def _async_update(event=None) -> None:
            self.async_write_ha_state()

        # Écoute le changement d'état du cover parent dans la machine d'état HA
        if hasattr(self._cover, "entity_id") and self._cover.entity_id:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._cover.entity_id],
                    _async_update,
                )
            )