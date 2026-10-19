"""Config and options flow for the Innova HRDS+ integration."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_AIRFLOW_MAX,
    CONF_HAS_DISPLAY,
    CONF_HOSTID,
    CONF_MODEL,
    DEFAULT_HAS_DISPLAY,
    DEFAULT_HOSTID,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MODEL_SPECS,
    MODELS,
)
from .identity import CannotConnect, WrongDevice, verify_device

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
        vol.Optional(CONF_HOSTID, default=DEFAULT_HOSTID): int,
        vol.Required(CONF_MODEL, default=DEFAULT_MODEL): vol.In(MODELS),
        vol.Optional(CONF_HAS_DISPLAY, default=DEFAULT_HAS_DISPLAY): cv.boolean,
    }
)


async def _check_device(
    hass: HomeAssistant, host: str, port: int, hostid: int
) -> str | None:
    """Return a form error key if the endpoint is not a reachable HRDS+."""
    try:
        await hass.async_add_executor_job(verify_device, host, port, hostid)
    except CannotConnect:
        return "cannot_connect"
    except WrongDevice:
        return "wrong_device"
    return None


def host_valid(host: str) -> bool:
    """Return True if hostname or IP address is valid."""
    try:
        return ipaddress.ip_address(host).version in (4, 6)
    except ValueError:
        disallowed = re.compile(r"[^a-zA-Z\d\-]")
        return all(x and not disallowed.search(x) for x in host.split("."))


@callback
def configured_hosts(hass: HomeAssistant) -> set[str]:
    return {
        entry.data.get(CONF_HOST) for entry in hass.config_entries.async_entries(DOMAIN)
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the user-driven config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            if host in configured_hosts(self.hass):
                errors[CONF_HOST] = "already_configured"
            elif not host_valid(host):
                errors[CONF_HOST] = "invalid_host"
            else:
                error = await _check_device(
                    self.hass,
                    host,
                    user_input.get(CONF_PORT, DEFAULT_PORT),
                    user_input.get(CONF_HOSTID, DEFAULT_HOSTID),
                )
                if error:
                    errors["base"] = error
                else:
                    await self.async_set_unique_id(host)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input[CONF_NAME], data=user_input
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            data = self.config_entry.data
            options = self.config_entry.options
            error = await _check_device(
                self.hass,
                user_input[CONF_HOST],
                user_input.get(
                    CONF_PORT, options.get(CONF_PORT, data.get(CONF_PORT, DEFAULT_PORT))
                ),
                user_input.get(
                    CONF_HOSTID,
                    options.get(CONF_HOSTID, data.get(CONF_HOSTID, DEFAULT_HOSTID)),
                ),
            )
            if error is None:
                return self.async_create_entry(title="", data=user_input)
            errors["base"] = error

        data = self.config_entry.data
        options = self.config_entry.options
        model = options.get(CONF_MODEL, data.get(CONF_MODEL, DEFAULT_MODEL))
        spec = (
            MODEL_SPECS[model] if model in MODEL_SPECS else MODEL_SPECS[DEFAULT_MODEL]
        )
        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=options.get(CONF_HOST, data.get(CONF_HOST)),
                    ): cv.string,
                    vol.Optional(
                        CONF_PORT,
                        default=options.get(
                            CONF_PORT, data.get(CONF_PORT, DEFAULT_PORT)
                        ),
                    ): cv.port,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=options.get(
                            CONF_SCAN_INTERVAL,
                            data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                        ),
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_HOSTID,
                        default=options.get(
                            CONF_HOSTID, data.get(CONF_HOSTID, DEFAULT_HOSTID)
                        ),
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_MODEL,
                        default=model,
                    ): vol.In(MODELS),
                    vol.Optional(
                        CONF_HAS_DISPLAY,
                        default=options.get(
                            CONF_HAS_DISPLAY,
                            data.get(CONF_HAS_DISPLAY, DEFAULT_HAS_DISPLAY),
                        ),
                    ): cv.boolean,
                    vol.Optional(
                        CONF_AIRFLOW_MAX,
                        default=options.get(
                            CONF_AIRFLOW_MAX,
                            data.get(CONF_AIRFLOW_MAX, spec["max"]),
                        ),
                    ): vol.Coerce(float),
                }
            ),
        )
