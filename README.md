# Umaimi Chef for Home Assistant

Your Umaimi Chef inventories and shopping lists in
Home Assistant, from your own self-hosted Umaimi Chef server.

- **Every list is a to-do list**: the inventories (freezer, pantry, fridge…) and the shopping lists. Add, rename, tick
  off and delete with Home Assistant's normal to-do actions; a new item gets the category it had last time.
  On an inventory, an item's best-before date is its due date.
- **The freezer card** (`custom:umamilist-freezer-card`): an inventory with each item's best-before date, coloured
  as it gets closer, with its quantity; add, tick off, rename and delete right on the card. It comes with the
  integration: no resource to add by hand.
- **`umamilist.add_item`** ("Add to a list"): add something with a quantity, and on an inventory the day it went in.

## Install

1. In HACS: ⋮ → **Custom repositories** → add `https://github.com/Velzeboer/umaimi-chef-homeassistant` as type
   **Integration**.
2. Install **Umaimi Chef**, then restart Home Assistant.
3. **Settings → Devices & services → Add integration → Umaimi Chef**: your server's address, and the email and
   password of your Umaimi Chef account. Home Assistant gets its own session; the password isn't stored.

Had the card before as a file in `/config/www` with a dashboard resource? Remove both: the integration now loads
the card itself.

## The freezer card

```yaml
type: custom:umamilist-freezer-card
entity: todo.freezer      # one of the inventories
title: Freezer            # optional
day_first: true           # optional: 31-12-2026 (true) or 12/31/2026 (false)
show_checked: true        # optional: false hides ticked-off items
```

## Adding from an automation

```yaml
action: umamilist.add_item
target:
  entity_id: todo.freezer
data:
  name: Kipfilet
  quantity: "2"
  frozen_on: "2026-10-30"   # inventories only; today if left out
```

On a shopping list the standard `todo.add_item` works just as well.

## Tests

The tests run the integration in Home Assistant's test harness against a real Umaimi Chef server:

```bash
pip install pytest-homeassistant-custom-component
UMAIMI_SERVER=/path/to/server/bin/server pytest
```

The integration's internal name is `umamilist` (its earlier name), so existing setups keep working.
