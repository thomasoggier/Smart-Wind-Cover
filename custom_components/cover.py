"""Plateforme Cover pour Smart Wind Cover Integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_CLOSED,
    STATE_OPEN,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
import homeassistant.util.dt as dt_util

from .const import (
    CONF_DELAY_OFF,
    CONF_MOVE_GA,
    CONF_PHYSICAL_COVER,
    CONF_STOP_GA,
    CONF_WIND_RULES,
    CONF_WIND_SENSOR,
    DEFAULT_DELAY_OFF,
    DEFAULT_WIND_RULES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configuration de la plateforme cover."""
    cover_entity = WindProtectedCoverEntity(hass, entry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id]["cover_entity"] = cover_entity

    async_add_entities([cover_entity])


class WindProtectedCoverEntity(CoverEntity):
    """Entité virtuelle du store avec protection vent multi-paliers et arbitrage KNX."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialisation du store virtuel."""
        self.hass = hass
        self._entry = entry

        options = entry.options
        data = entry.data

        def _get_setting(key: str, default: Any = None) -> Any:
            val = options.get(key)
            if val is not None and val != "":
                return val
            val = data.get(key)
            if val is not None and val != "":
                return val
            return default

        self._physical_cover = _get_setting(CONF_PHYSICAL_COVER)
        self._wind_sensor_entity = _get_setting(CONF_WIND_SENSOR)

        raw_move = _get_setting(CONF_MOVE_GA)
        raw_stop = _get_setting(CONF_STOP_GA)
        self._move_ga = str(raw_move).strip().replace(".", "/") if raw_move else None
        self._stop_ga = str(raw_stop).strip().replace(".", "/") if raw_stop else None

        self._attr_unique_id = f"{entry.entry_id}_cover"
        state = hass.states.get(self._physical_cover) if self._physical_cover else None
        self._attr_name = f"Store Protégé ({state.name if state else self._physical_cover})"

        initial_position = 100
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            phys_pos = state.attributes.get(ATTR_CURRENT_POSITION)
            if phys_pos is not None:
                initial_position = int(phys_pos)

        self._current_position: int | None = initial_position
        self._user_consigne: int = initial_position
        self._safety_limit: int = 0
        self._target_position: int | None = initial_position  # Suivi de la cible en cours
        self._is_manual_stopped = False
        self._last_trigger_times: dict[float, dt_util.datetime | None] = {}
        self._unsub_timer = None

    @property
    def parsed_wind_rules(self) -> list[dict[str, float]]:
        """Parse le paramètre '35:50, 50:100' en une liste de règles triées."""
        raw_rules = self._entry.options.get(
            CONF_WIND_RULES,
            self._entry.data.get(CONF_WIND_RULES, DEFAULT_WIND_RULES),
        )
        rules = []
        try:
            for item in raw_rules.split(","):
                if ":" in item:
                    vent_str, pos_str = item.split(":")
                    rules.append({
                        "vent": float(vent_str.strip()),
                        "min_repli": float(pos_str.strip()),
                    })
            rules.sort(key=lambda r: r["vent"])
        except Exception as err:
            _LOGGER.error("Erreur de formatage des règles de vent '%s': %s", raw_rules, err)
        return rules

    @property
    def delay_off(self) -> int:
        """Délai de sécurité après accalmie."""
        return self._entry.options.get(
            CONF_DELAY_OFF,
            self._entry.data.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF),
        )

    @property
    def supported_features(self) -> CoverEntityFeature:
        features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
        )
        if self._stop_ga or self._physical_cover:
            features |= CoverEntityFeature.STOP
        return features

    @property
    def current_cover_position(self) -> int | None:
        return self._current_position

    @property
    def is_closed(self) -> bool | None:
        if self._current_position is None:
            return None
        return self._current_position == 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "user_consigne": self._user_consigne,
            "safety_limit": self._safety_limit,
            "target_position": self._target_position,
            "wind_rules": self.parsed_wind_rules,
            "wind_sensor": self._wind_sensor_entity,
            "physical_cover": self._physical_cover,
            "delay_off": self.delay_off,
            "safety_active": self._safety_limit > 0,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        gas_to_register = []
        if self._move_ga:
            gas_to_register.append(str(self._move_ga))
        if self._stop_ga:
            gas_to_register.append(str(self._stop_ga))

        if gas_to_register:
            try:
                await self.hass.services.async_call(
                    "knx",
                    "event_register",
                    {"address": gas_to_register},
                    blocking=True,
                )
                _LOGGER.debug("[%s] GA KNX enregistrées avec succès : %s", self._attr_name, gas_to_register)
            except Exception as err:
                _LOGGER.error("[%s] Échec de l'enregistrement des GA KNX : %s", self._attr_name, err)

        self.async_on_remove(
            self.hass.bus.async_listen("knx_event", self._handle_knx_event)
        )
        
        if self._wind_sensor_entity:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._wind_sensor_entity],
                    self._async_wind_sensor_changed,
                )
            )

        if self._physical_cover:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._physical_cover],
                    self._async_physical_cover_changed,
                )
            )

        await self._async_apply_arbitration()

    async def _async_wind_sensor_changed(self, event: Event) -> None:
        await self._async_apply_arbitration()

    async def _handle_knx_event(self, event: Event) -> None:
        """Handle knx event on Open/Close/Stop cover"""
        telegram_data = event.data
        destination = str(telegram_data.get("destination", "")).strip()
        if destination not in (self._move_ga, self._stop_ga):
            return

        value = telegram_data.get("data")
        if value is None:
            payload = telegram_data.get("payload")
            if isinstance(payload, list) and len(payload) > 0:
                value = payload[0]
            elif isinstance(payload, int):
                value = payload

        if destination == self._move_ga:
            if value == 0:
                _LOGGER.debug("[%s] Poussoir KNX: Ordre OUVERTURE", self._attr_name)
                await self.async_open_cover()
            elif value == 1:
                _LOGGER.debug("[%s] Poussoir KNX: Ordre FERMETURE", self._attr_name)
                await self.async_close_cover()
            else:
                _LOGGER.warning("[%s] Poussoir KNX: Ordre inconnu: %s", self._attr_name, value)

        elif destination == self._stop_ga:
            _LOGGER.debug("[%s] Poussoir KNX: Ordre STOP", self._attr_name)
            await self.async_stop_cover()

    async def async_open_cover(self, **kwargs: Any) -> None:
        _LOGGER.debug("Action UI/KNX: Demande ouverture complète (100)")
        await self.async_set_cover_position(**{ATTR_POSITION: 100})

    async def async_close_cover(self, **kwargs: Any) -> None:
        _LOGGER.debug("Action UI/KNX: Demande fermeture complète (0)")
        await self.async_set_cover_position(**{ATTR_POSITION: 0})

    async def async_stop_cover(self, **kwargs: Any) -> None:
        _LOGGER.debug("Action: Demande STOP")
        self._is_manual_stopped = True
        if self._physical_cover:
            await self.hass.services.async_call(
                "cover",
                "stop_cover",
                {"entity_id": self._physical_cover},
                blocking=False,
            )

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get(ATTR_POSITION)
        if position is None:
            return

        self._user_consigne = int(position)
        self.async_write_ha_state()
        _LOGGER.info("Consigne utilisateur mise à jour: %s%%", self._user_consigne)
        await self._async_apply_arbitration()

    def _get_max_allowed_position(self) -> float:
        now = dt_util.now()

        active_limits = [0.0]
        delay_delta = timedelta(seconds=self.delay_off)
        next_expiration: float | None = None

        wind_speed = self._get_wind_speed()

        for rule in self.parsed_wind_rules:
            seuil_vent = rule["vent"]
            min_repli = rule["min_repli"]

            if wind_speed >= seuil_vent:
                self._last_trigger_times[min_repli] = None
                active_limits.append(min_repli)
            else:
                if min_repli in self._last_trigger_times:
                    if self._last_trigger_times[min_repli] is None:
                        self._last_trigger_times[min_repli] = now
                        _LOGGER.info(
                            "[%s] Vent sous le seuil %skm/h (actuel: %skm/h) -> Début de l'accalmie (%ss)",
                            self._attr_name, seuil_vent, wind_speed, self.delay_off
                        )

                    last_time = self._last_trigger_times[min_repli]
                    if last_time is not None:
                        time_calm = now - last_time

                        if time_calm < delay_delta:
                            active_limits.append(min_repli)
                            remaining = (delay_delta - time_calm).total_seconds()
                            if next_expiration is None or remaining < next_expiration:
                                next_expiration = remaining
                        else:
                            _LOGGER.info(
                                "[%s] Accalmie validée -> Levée de la contrainte %s%%",
                                self._attr_name, min_repli
                            )
                            del self._last_trigger_times[min_repli]

        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

        if next_expiration is not None and next_expiration > 0:
            async def _scheduled_update(now_dt):
                self._unsub_timer = None
                await self._async_apply_arbitration()

            self._unsub_timer = async_call_later(
                self.hass, next_expiration + 0.1, _scheduled_update
            )

        return max(active_limits)

    def _get_wind_speed(self):
        try:
            wind_state = self.hass.states.get(self._wind_sensor_entity)
            return float(wind_state.state) if wind_state and wind_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN) else 0.0
        except (AttributeError, ValueError, TypeError):
            _LOGGER.warning("[%s] Lecture impossible du capteur de vent", self._attr_name)
            return 0.0

    async def _async_apply_arbitration(self) -> None:
        """Calcul : target = max(user_consigne, safety_limit)."""
        max_allowed = self._get_max_allowed_position()
        self._safety_limit = int(max_allowed)
        target_position = max(self._user_consigne, self._safety_limit)
        self.async_write_ha_state()

        # Ne re-transmet l'ordre que si la CIBLE a changé
        if self._target_position != target_position:
            self._target_position = target_position
            self.async_write_ha_state()

            _LOGGER.debug(
                "Envoi ordre -> Consigne User: %s, Sécurité Vent: %s%% (%skm/h) => Cible appliquée: %s%% sur %s",
                self._user_consigne,
                self._safety_limit,
                self._get_wind_speed(),
                self._target_position,
                self._physical_cover or self._move_ga,
            )
            self.async_write_ha_state()

            if self._physical_cover:
                await self.hass.services.async_call(
                    "cover",
                    "set_cover_position",
                    {
                        "entity_id": self._physical_cover,
                        "position": target_position,
                    },
                    blocking=False,
                )
        self.async_write_ha_state()

    async def _async_physical_cover_changed(self, event: Event) -> None:
        """Recopie de l'état réel et du retour d'information du store physique."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        pos = new_state.attributes.get(ATTR_CURRENT_POSITION)
        if pos is not None:
            self._current_position = int(pos)
            _LOGGER.debug("Retour d'état physique (position) : %s%%", self._current_position)


        if self._is_manual_stopped and self._current_position is not None:
            self._user_consigne = self._current_position
            self.async_write_ha_state()
            _LOGGER.info(
                "Consigne utilisateur mise à jour par bouton stop: %s%%",
                self._user_consigne
            )
            self._is_manual_stopped = False

        self.async_write_ha_state()