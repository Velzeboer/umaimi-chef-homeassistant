"""A to-do list entity per Umaimi Chef list: the inventories (freezer, pantry…) and the shopping lists.

The standard to-do services work on both. On an inventory the best-before date is shown as the due
date, and the freezer card reads the full items from the `items` attribute: freeze date, quantity,
category, shelf life and when an item was checked off. A shopping list's `items` attribute has each
item's category, in the list's order; the freezer card leaves shopping lists alone.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import UmamiListError
from .const import DEFAULT_SHELF_LIFE_MONTHS
from .coordinator import ListData, UmamiListConfigEntry, UmamiListCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: UmamiListConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def add_new_lists() -> None:
        """Every list gets its entity, also one made after Home Assistant started."""
        new = [list_id for list_id in coordinator.data if list_id not in added]
        added.update(new)
        async_add_entities(
            (UmamiListTodoEntity if coordinator.data[list_id].list["type"] == "freezer" else UmamiListShoppingEntity)(coordinator, list_id)
            for list_id in new
        )

    add_new_lists()
    entry.async_on_unload(coordinator.async_add_listener(add_new_lists))
    entity_platform.async_get_current_platform().async_register_entity_service(
        "add_item",
        {
            vol.Required("name"): cv.string,
            vol.Optional("quantity"): cv.string,
            vol.Optional("frozen_on"): cv.date,
            vol.Optional("notes"): cv.string,
        },
        "async_add_freezer_item",
    )


def add_months(day: date, months: int) -> date:
    """Like the app: 31 January plus one month is the last day of February."""
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    return day.replace(year=year, month=month + 1, day=min(day.day, calendar.monthrange(year, month + 1)[1]))


class UmamiListBaseEntity(CoordinatorEntity[UmamiListCoordinator], TodoListEntity):
    """What an inventory and a shopping list have in common: renaming, notes, ticking off and deleting."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )
    # The items are in the state attributes (for the card); no need to store them in the history.
    _unrecorded_attributes = frozenset({"items"})

    def __init__(self, coordinator: UmamiListCoordinator, list_id: str) -> None:
        super().__init__(coordinator)
        self._list_id = list_id
        self._attr_unique_id = list_id
        self._attr_name = coordinator.data[list_id].list["name"]

    @property
    def _data(self) -> ListData | None:
        return self.coordinator.data.get(self._list_id)

    @property
    def available(self) -> bool:
        return super().available and self._data is not None

    def _details(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._data is not None:
            self._attr_name = self._data.list["name"]
        super()._handle_coordinator_update()

    async def _call(self, request) -> Any:
        """Runs a request to the server, then fetches the list again so the change shows at once."""
        try:
            result = await request
        except UmamiListError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_refresh()
        return result

    def _remembered_category(self, name: str) -> str | None:
        data = self._data
        return data.remembered.get(name.strip().lower()) if data else None

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """todo.update_item: the name (when renamed), the notes and ticking off."""
        current = next((it for it in self._details() if it["uid"] == item.uid), None)
        if current is None:
            raise HomeAssistantError("This item no longer exists")
        changes: dict[str, Any] = {}
        # The summary shows the quantity after the name; a rename that keeps it changes only the name.
        suffix = f" ({current['quantity']})" if current["quantity"] else ""
        name = (item.summary or "").strip()
        if suffix and name.endswith(suffix):
            name = name.removesuffix(suffix).strip()
        if name and name != current["name"]:
            changes["name"] = name
        if (item.description or "") != current["notes"]:
            changes["notes"] = (item.description or "").strip()
        checked = item.status == TodoItemStatus.COMPLETED
        if checked != current["checked"]:
            changes["checked"] = checked
        if changes:
            await self._call(self.coordinator.api.edit_item(item.uid, changes))

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            try:
                await self.coordinator.api.delete_item(uid)
            except UmamiListError as err:
                raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_refresh()


class UmamiListTodoEntity(UmamiListBaseEntity):
    """An inventory (freezer, pantry…): items with the date they went in and their best-before date."""

    def _details(self) -> list[dict[str, Any]]:
        """The items with everything the card needs, the category's name and shelf life filled in."""
        data = self._data
        if data is None:
            return []
        categories = {c["id"]: c for c in data.categories}
        result = []
        for it in data.items:
            category = categories.get(it["categoryId"])
            months = (category or {}).get("shelfLifeMonths")
            # A fridge's categories keep for days instead of months.
            days = (category or {}).get("shelfLifeDays")
            frozen = date.fromisoformat(it["frozenOn"]) if it["frozenOn"] else None
            if frozen is None:
                best_before = None
            elif days:
                best_before = (frozen + timedelta(days=days)).isoformat()
            else:
                best_before = add_months(frozen, months or DEFAULT_SHELF_LIFE_MONTHS).isoformat()
            result.append({
                "uid": it["id"],
                "name": it["name"],
                "quantity": it["quantity"],
                "notes": it["notes"],
                "frozen_on": it["frozenOn"],
                "best_before": best_before,
                "category": category["name"] if category else None,
                "shelf_life_months": months,
                "shelf_life_days": days,
                "checked": it["checked"],
                "checked_at": it["checkedAt"],
            })
        return result

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=it["uid"],
                summary=it["name"] + (f" ({it['quantity']})" if it["quantity"] else ""),
                status=TodoItemStatus.COMPLETED if it["checked"] else TodoItemStatus.NEEDS_ACTION,
                due=date.fromisoformat(it["best_before"]) if it["best_before"] else None,
                description=it["notes"] or None,
            )
            for it in self._details()
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"umamilist": True, "items": self._details()}

    async def async_add_freezer_item(
        self, name: str, quantity: str | None = None, frozen_on: date | None = None, notes: str | None = None
    ) -> None:
        """The umamilist.add_item service."""
        await self._call(self.coordinator.api.add_item(self._list_id, {
            "name": name.strip(),
            "quantity": (quantity or "").strip() or None,
            "notes": (notes or "").strip(),
            "frozenOn": (frozen_on or dt_util.now().date()).isoformat(),
            "categoryId": self._remembered_category(name),
        }))

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """todo.add_item: frozen today, in the category last used for this name."""
        await self.async_add_freezer_item(item.summary or "", notes=item.description)


class UmamiListShoppingEntity(UmamiListBaseEntity):
    """A shopping list: things to get, in the list's category order, ticked off when you have them."""

    def _details(self) -> list[dict[str, Any]]:
        data = self._data
        if data is None:
            return []
        categories = {c["id"]: c for c in data.categories}
        use_categories = data.list.get("useCategories", True)
        # As the app groups them: by the categories' order (the shop's), uncategorised last; then as added.
        def order(it: dict[str, Any]) -> tuple[int, int]:
            category = categories.get(it["categoryId"]) if use_categories else None
            return (category["sortOrder"] if category else 1_000_000, it.get("createdAt", 0))
        return [
            {
                "uid": it["id"],
                "name": it["name"],
                "quantity": it["quantity"],
                "notes": it["notes"],
                "brand": it.get("brand"),
                "category": categories[it["categoryId"]]["name"] if use_categories and it["categoryId"] in categories else None,
                "checked": it["checked"],
                "checked_at": it["checkedAt"],
            }
            for it in sorted(data.items, key=order)
        ]

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=it["uid"],
                summary=it["name"] + (f" ({it['quantity']})" if it["quantity"] else ""),
                status=TodoItemStatus.COMPLETED if it["checked"] else TodoItemStatus.NEEDS_ACTION,
                description=it["notes"] or None,
            )
            for it in self._details()
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Not "umamilist": that's how the freezer card finds an inventory.
        return {"umamilist_shopping": True, "items": self._details()}

    async def async_add_freezer_item(
        self, name: str, quantity: str | None = None, frozen_on: date | None = None, notes: str | None = None
    ) -> None:
        """The umamilist.add_item service on a shopping list: no date there."""
        data = self._data
        await self._call(self.coordinator.api.add_item(self._list_id, {
            "name": name.strip(),
            "quantity": (quantity or "").strip() or None,
            "notes": (notes or "").strip(),
            "categoryId": self._remembered_category(name) if data and data.list.get("useCategories", True) else None,
        }))

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """todo.add_item: in the category last used for this name."""
        await self.async_add_freezer_item(item.summary or "", notes=item.description)
