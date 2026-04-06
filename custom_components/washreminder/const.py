"""Constants for the Wash Reminder integration."""

DOMAIN = "washreminder"

# ---------------------------------------------------------------------------
# Timing defaults
# ---------------------------------------------------------------------------
DEFAULT_SNOOZE_MINUTES = 15
DEFAULT_REPEAT_INTERVAL_MINUTES = 30
DEFAULT_MAX_REPEATS = 10
DEFAULT_ARRIVAL_DELAY_SECONDS = 30

# ---------------------------------------------------------------------------
# Notification constants
# ---------------------------------------------------------------------------
NOTIFICATION_TAG = "washreminder"

# Static action IDs — safe because the tag ensures only one notification is
# active at a time, and _wait_for_action listeners are scoped per loop
# iteration and torn down on cancel / timeout.
ACTION_SNOOZE = "WASHREMINDER_SNOOZE"
ACTION_DONE = "WASHREMINDER_DONE"

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
STORAGE_KEY = "washreminder_state"
STORAGE_VERSION = 1

# ---------------------------------------------------------------------------
# Config / options keys
# ---------------------------------------------------------------------------
CONF_TRIGGER_ENTITY = "trigger_entity"
CONF_TRIGGER_STATE = "trigger_state"          # "" = binary sensor (on→off)
CONF_PERSON = "person_entity_id"
CONF_NOTIFY_TARGET = "notify_target"
CONF_DOOR_SENSOR = "door_sensor_entity_id"    # Optional contact sensor on machine door
CONF_DOOR_SENSOR_INVERTED = "door_sensor_inverted"  # True = "off" means open
CONF_SNOOZE_MINUTES = "snooze_minutes"
CONF_REPEAT_INTERVAL_MINUTES = "repeat_interval_minutes"
CONF_MAX_REPEATS = "max_repeats"
CONF_ARRIVAL_DELAY_SECONDS = "arrival_delay_seconds"

# ---------------------------------------------------------------------------
# Trigger state defaults
# ---------------------------------------------------------------------------
DEFAULT_BINARY_SENSOR_TRIGGER_STATE = ""      # Sentinel: use on→off logic
