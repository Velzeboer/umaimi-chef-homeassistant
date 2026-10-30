"""Constants for the Umaimi Chef integration (its domain stays "umamilist", so existing setups keep working)."""

from datetime import timedelta

DOMAIN = "umamilist"
VERSION = "0.2.0"

# Where the integration serves the freezer card (it's loaded on every dashboard).
CARD_URL = "/umamilist/umamilist-freezer-card.js"

CONF_TOKEN = "token"

# How often the lists are fetched from the server; changes made from Home Assistant show up at once.
UPDATE_INTERVAL = timedelta(seconds=30)

# Shelf life for items without a category, or in one without a shelf life (same as the app).
DEFAULT_SHELF_LIFE_MONTHS = 12
