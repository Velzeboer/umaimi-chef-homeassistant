"""End-to-end tests: config flow, the to-do entity and the add_item service against a real server."""

from datetime import date, timedelta
import json
import urllib.request

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from custom_components.umamilist.const import CARD_URL, DOMAIN
from custom_components.umamilist.todo import add_months

from .conftest import EMAIL, PASSWORD

ENTITY = "todo.freezer"


async def _setup(hass: HomeAssistant, server: str):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": server, "email": EMAIL, "password": PASSWORD}
    )
    await hass.async_block_till_done()
    return result


def _items(hass: HomeAssistant) -> list[dict]:
    return hass.states.get(ENTITY).attributes["items"]


async def test_config_flow_errors_then_success(hass: HomeAssistant, server: str) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": server, "email": EMAIL, "password": "wrong password"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": "http://127.0.0.1:1", "email": EMAIL, "password": PASSWORD}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": server + "/", "email": EMAIL, "password": PASSWORD}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Umaimi Chef ({EMAIL})"
    assert result["data"]["url"] == server
    assert "password" not in result["data"]
    assert hass.states.get(ENTITY) is not None

    # The same account can't be added twice.
    again = await _setup(hass, server)
    assert again["type"] is FlowResultType.ABORT
    assert again["reason"] == "already_configured"


async def test_add_item_service_and_remembered_category(hass: HomeAssistant, server: str, login, api_post) -> None:
    # Give "kipfilet" a remembered category on the server, like adding it once in the app would.
    token = login()
    lists = json.loads(urllib.request.urlopen(urllib.request.Request(
        server + "/api/lists", headers={"Authorization": f"Bearer {token}"})).read())
    list_id = lists[0]["id"]
    categories = json.loads(urllib.request.urlopen(urllib.request.Request(
        server + f"/api/lists/{list_id}/categories", headers={"Authorization": f"Bearer {token}"})).read())
    kip = next(c for c in categories["categories"] if c["name"] == "Chicken")
    api_post(f"/api/lists/{list_id}/items", {"name": "Kipfilet", "categoryId": kip["id"]}, token)

    await _setup(hass, server)
    await hass.services.async_call(
        DOMAIN, "add_item",
        {"name": "kipfilet", "quantity": "2", "frozen_on": "2026-09-05", "notes": "4 stuks"},
        target={"entity_id": ENTITY}, blocking=True,
    )
    added = next(it for it in _items(hass) if it["name"] == "kipfilet")
    assert added["quantity"] == "2"
    assert added["notes"] == "4 stuks"
    assert added["frozen_on"] == "2026-09-05"
    assert added["category"] == "Chicken"
    assert added["shelf_life_months"] == 9
    assert added["best_before"] == "2027-06-05"


async def test_standard_todo_services(hass: HomeAssistant, server: str) -> None:
    await _setup(hass, server)
    await hass.services.async_call("todo", "add_item", {"item": "Soep", "description": "2 porties"},
                                   target={"entity_id": ENTITY}, blocking=True)
    soep = _items(hass)[0]
    assert soep["frozen_on"] == dt_util.now().date().isoformat()  # today, when added the standard way
    assert soep["category"] is None
    assert soep["notes"] == "2 porties"
    assert hass.states.get(ENTITY).state == "1"  # items still to do

    # The standard list shows the quantity after the name and the best-before date as due date.
    await hass.services.async_call(DOMAIN, "add_item", {"name": "Brood", "quantity": "1"},
                                   target={"entity_id": ENTITY}, blocking=True)
    got = await hass.services.async_call("todo", "get_items", target={"entity_id": ENTITY},
                                         blocking=True, return_response=True)
    brood = next(i for i in got[ENTITY]["items"] if i["summary"].startswith("Brood"))
    assert brood["summary"] == "Brood (1)"
    assert brood["due"] == add_months(dt_util.now().date(), 12).isoformat()

    # Renaming "Brood (1)" to "Bruin brood (1)": only the name changes; the quantity stays.
    await hass.services.async_call("todo", "update_item", {"item": brood["uid"], "rename": "Bruin brood"},
                                   target={"entity_id": ENTITY}, blocking=True)
    renamed = next(it for it in _items(hass) if it["uid"] == brood["uid"])
    assert renamed["name"] == "Bruin brood"
    assert renamed["quantity"] == "1"

    # Renamed in Home Assistant's own to-do list, where the quantity is part of the shown name.
    await hass.services.async_call("todo", "update_item", {"item": brood["uid"], "rename": "Wit brood (1)"},
                                   target={"entity_id": ENTITY}, blocking=True)
    renamed = next(it for it in _items(hass) if it["uid"] == brood["uid"])
    assert renamed["name"] == "Wit brood"
    assert renamed["quantity"] == "1"

    await hass.services.async_call("todo", "update_item", {"item": soep["uid"], "status": "completed"},
                                   target={"entity_id": ENTITY}, blocking=True)
    checked = next(it for it in _items(hass) if it["uid"] == soep["uid"])
    assert checked["checked"] is True
    assert checked["checked_at"] is not None

    await hass.services.async_call("todo", "remove_item", {"item": [soep["uid"]]},
                                   target={"entity_id": ENTITY}, blocking=True)
    assert [it["uid"] for it in _items(hass)] == [brood["uid"]]


async def test_shopping_list_is_a_todo_list_of_its_own(hass: HomeAssistant, server: str, login, api_post) -> None:
    # Give "melk" a remembered category on the shopping list, like adding it once in the app would.
    token = login()
    lists = json.loads(urllib.request.urlopen(urllib.request.Request(
        server + "/api/lists", headers={"Authorization": f"Bearer {token}"})).read())
    shop = next(lst for lst in lists if lst["type"] == "grocery")
    categories = json.loads(urllib.request.urlopen(urllib.request.Request(
        server + f"/api/lists/{shop['id']}/categories", headers={"Authorization": f"Bearer {token}"})).read())["categories"]
    dairy = next(c for c in categories if c["name"].startswith("Dairy"))
    api_post(f"/api/lists/{shop['id']}/items", {"name": "Melk", "categoryId": dairy["id"]}, token)

    await _setup(hass, server)
    entity = "todo.shopping_list"
    state = hass.states.get(entity)
    assert state is not None and state.state == "1"
    # The freezer card looks for "umamilist": a shopping list never has it, so the card can't pick it.
    assert "umamilist" not in state.attributes
    assert state.attributes["umamilist_shopping"] is True

    await hass.services.async_call("todo", "add_item", {"item": "melk", "description": "halfvol"},
                                   target={"entity_id": entity}, blocking=True)
    await hass.services.async_call(DOMAIN, "add_item", {"name": "Brood", "quantity": "2", "frozen_on": "2026-09-05"},
                                   target={"entity_id": entity}, blocking=True)
    items = hass.states.get(entity).attributes["items"]
    added = next(it for it in items if it["name"] == "melk")
    assert added["category"] == dairy["name"]
    assert added["notes"] == "halfvol"
    brood = next(it for it in items if it["name"] == "Brood")
    assert brood["quantity"] == "2" and brood["category"] is None
    assert "frozen_on" not in brood  # no dates on a shopping list
    # In the shop's order: the dairy before what has no category.
    assert [it["name"] for it in items].index("Brood") > [it["name"] for it in items].index("melk")

    got = await hass.services.async_call("todo", "get_items", target={"entity_id": entity}, blocking=True, return_response=True)
    assert any(i["summary"] == "Brood (2)" and "due" not in i for i in got[entity]["items"])
    await hass.services.async_call("todo", "update_item", {"item": brood["uid"], "status": "completed"},
                                   target={"entity_id": entity}, blocking=True)
    assert next(it for it in hass.states.get(entity).attributes["items"] if it["uid"] == brood["uid"])["checked"] is True
    await hass.services.async_call("todo", "remove_item", {"item": [brood["uid"]]}, target={"entity_id": entity}, blocking=True)
    assert all(it["uid"] != brood["uid"] for it in hass.states.get(entity).attributes["items"])

    # A list made later gets its entity without restarting.
    api_post("/api/lists", {"type": "grocery", "name": "BBQ"}, token)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("todo.bbq") is not None


async def test_ended_session_asks_to_log_in_again(hass: HomeAssistant, server: str) -> None:
    await _setup(hass, server)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    token = entry.data["token"]

    # End Home Assistant's session on the server, then let it refresh.
    urllib.request.urlopen(urllib.request.Request(
        server + "/api/auth/logout", method="POST", headers={"Authorization": f"Bearer {token}"}))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]

    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {"password": PASSWORD})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] != token
    assert entry.state is ConfigEntryState.LOADED


async def test_the_card_comes_with_the_integration(hass: HomeAssistant, server: str, hass_client) -> None:
    await _setup(hass, server)
    client = await hass_client()
    resp = await client.get(CARD_URL)
    assert resp.status == 200
    assert 'customElements.define("umamilist-freezer-card"' in await resp.text()


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert add_months(date(2026, 3, 1), 12) - date(2026, 3, 1) == timedelta(days=365)
