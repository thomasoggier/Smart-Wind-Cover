"""Tests unitaires pour la plateforme Cover de Smart Wind Cover."""
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.smart_wind_cover.const import (
    CONF_DELAY_OFF,
    CONF_MOVE_GA,
    CONF_PHYSICAL_COVER,
    CONF_STOP_GA,
    CONF_WIND_RULES,
    CONF_WIND_SENSOR,
    DOMAIN,
)


async def setup_mock_entity(
    hass: HomeAssistant,
    entry_data: dict,
    entry_options: dict = None,
):
    """Helper pour initialiser l'intégration de test."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data,
        options=entry_options or {},
        entry_id="test_entry_id",
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new_callable=AsyncMock,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_initialization_defaults(hass: HomeAssistant) -> None:
    """Teste l'initialisation sans état physique préalable."""
    entry_data = {
        CONF_PHYSICAL_COVER: "cover.salon_physique",
        CONF_WIND_SENSOR: "sensor.vent_exterieur",
        CONF_MOVE_GA: "2/2/211",
        CONF_STOP_GA: "2/2/212",
        CONF_WIND_RULES: "35:50, 50:100",
        CONF_DELAY_OFF: 60,
    }
    await setup_mock_entity(hass, entry_data)

    entity_id = "cover.store_protege_cover_salon_physique"
    state = hass.states.get(entity_id)

    assert state is not None
    assert state.attributes["user_consigne"] == 100
    assert state.attributes["safety_limit"] == 0
    assert state.attributes["safety_active"] is False


async def test_initialization_from_physical_state(hass: HomeAssistant) -> None:
    """Teste l'initialisation basée sur la position actuelle du store physique."""
    hass.states.async_set(
        "cover.salon_physique",
        "open",
        {ATTR_CURRENT_POSITION: 75},
    )

    entry_data = {
        CONF_PHYSICAL_COVER: "cover.salon_physique",
        CONF_WIND_SENSOR: "sensor.vent_exterieur",
    }
    await setup_mock_entity(hass, entry_data)

    entity_id = "cover.store_protege_salon_physique"
    state = hass.states.get(entity_id)

    assert state.attributes[ATTR_CURRENT_POSITION] == 75
    assert state.attributes["user_consigne"] == 75


async def test_wind_safety_trigger_and_arbitration(hass: HomeAssistant) -> None:
    """Teste la prise de priorité du vent sur la consigne utilisateur."""
    entry_data = {
        CONF_PHYSICAL_COVER: "cover.salon_physique",
        CONF_WIND_SENSOR: "sensor.vent_exterieur",
        CONF_WIND_RULES: "30:50, 50:100",
        CONF_DELAY_OFF: 10,
    }
    await setup_mock_entity(hass, entry_data)

    entity_id = "cover.store_protege_salon_physique"

    # 1. Vent normal (20 km/h) -> aucune contrainte
    hass.states.async_set("sensor.vent_exterieur", "20.0")
    await hass.async_block_till_done()

    # 2. Vent modéré (35 km/h) -> limite min à 50%
    with patch.object(hass.services, "async_call") as mock_service:
        hass.states.async_set("sensor.vent_exterieur", "35.0")
        await hass.async_block_till_done()

        state = hass.states.get(entity_id)
        assert state.attributes["safety_limit"] == 50
        assert state.attributes["safety_active"] is True


async def test_knx_event_handling(hass: HomeAssistant) -> None:
    """Teste le traitement des ordres de commandes KNX."""
    entry_data = {
        CONF_PHYSICAL_COVER: "cover.salon_physique",
        CONF_MOVE_GA: "2/2/211",
        CONF_STOP_GA: "2/2/212",
    }
    await setup_mock_entity(hass, entry_data)

    # Simulation de l'émission d'un télégramme KNX "Fermeture" (value 1)
    with patch.object(hass.services, "async_call") as mock_service:
        hass.bus.async_fire(
            "knx_event",
            {"destination": "2/2/211", "data": 1},
        )
        await hass.async_block_till_done()

        # Doit appeler l'ordre d'abaissement
        mock_service.assert_called()


async def test_manual_movement_capture(hass: HomeAssistant) -> None:
    """Teste la mise à jour de la consigne lors d'un déplacement manuel."""
    entry_data = {
        CONF_PHYSICAL_COVER: "cover.salon_physique",
        CONF_MOVE_GA: "2/2/211",
    }
    await setup_mock_entity(hass, entry_data)

    entity_id = "cover.store_protege_salon_physique"

    # Déclenchement d'un ordre KNX
    hass.bus.async_fire("knx_event", {"destination": "2/2/211", "data": 0})
    await hass.async_block_till_done()

    # Changement d'état du store physique
    hass.states.async_set(
        "cover.salon_physique",
        "open",
        {ATTR_CURRENT_POSITION: 40},
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.attributes["user_consigne"] == 40