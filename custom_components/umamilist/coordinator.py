"""Fetches the lists from the Umaimi Chef server for all entities of one account."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UmamiListApi, UmamiListAuthError, UmamiListError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type UmamiListConfigEntry = ConfigEntry[UmamiListCoordinator]


@dataclass
class ListData:
    """One list as the server has it: the list, its items and its categories."""

    list: dict[str, Any]
    items: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    remembered: dict[str, str]


class UmamiListCoordinator(DataUpdateCoordinator[dict[str, ListData]]):
    """Data per list id: the inventories (type freezer) and the shopping lists (type grocery)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: UmamiListApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.api = api

    async def _async_update_data(self) -> dict[str, ListData]:
        try:
            data = {}
            for lst in await self.api.lists():
                if lst["type"] not in ("freezer", "grocery"):
                    continue
                categories = await self.api.categories(lst["id"])
                data[lst["id"]] = ListData(
                    lst, await self.api.items(lst["id"]), categories["categories"], categories["remembered"]
                )
            return data
        except UmamiListAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UmamiListError as err:
            raise UpdateFailed(str(err)) from err
