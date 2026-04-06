# Changelog

All notable changes to Wash Reminder will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] - 2026-04-06

### ⚠️ Breaking
- **Domain renamed** from `washdata_reminder` to `washreminder`. Existing installs must be removed and re-added — the config entry, storage file (`.storage/washreminder_state`), logger path (`custom_components.washreminder`), and notification tag (`washreminder`) have all changed. The display name is now "Wash Reminder".

### Added
- **Door contact sensor** — optional binary sensor on the machine door. Opening the door cancels all active reminders, clears any saved pending state, and stops arrival delivery tasks.
- **Invert door sensor** — toggle for contact sensors that report "off" when the door is open. Useful for Zigbee and other sensors that don't follow the Home Assistant convention.
- **Arrival delay setting** — configurable grace period (0–120 s) before notifying after arriving home. Gives the phone time to reconnect to WiFi so notification actions work reliably.
- **Notify service validation** — the config flow checks that the notification service exists before saving, catching typos at setup time.
- Delivery task tracking to prevent duplicate notification loops when a new cycle completes while a previous arrival delivery is still in progress.
- Diagnostics now shows door sensor status, polarity, and delivery task state.

### Changed
- Notification action IDs are now static (`WASHREMINDER_SNOOZE`, `WASHREMINDER_DONE`) instead of timestamped. Since notifications use a fixed tag, only one is active at a time.
- Snooze button text no longer hardcodes "15 min" — just says "Snooze", which stays correct regardless of the configured duration.
- Notification text updated: "Time to empty the washing machine." / "The laundry is still waiting."
- All config flow labels and descriptions rewritten for clarity and consistency.
- Exception messages now use a consistent "Could not find …" / "Could not send …" pattern.
- `@property` accessors on the coordinator replace direct private attribute access in diagnostics.
- Notify service errors are now caught and logged — the reminder loop stops cleanly instead of crashing silently.
- Notification service normalisation now strips all leading `notify.` prefixes, handling double-prefix typos like `notify.notify.mobile_app_foo`.
- Config flow initialisation moved from a mutable class-level default to a proper `__init__` method.
- Door sensor entity selector uses `vol.Optional` without a default value, preventing `EntitySelector` from validating an empty string as an entity ID.
- Door sensor can now be removed after initial setup via the reconfigure flow.
- Translation file loading deduplicates the language fallback when HA is already set to English.
- Door-open events produce a single consolidated log line instead of multiple separate entries.

### Fixed
- Duplicate entries removed from `quality_scale.yaml`.
- Brace-expansion artifact directories removed from release zip.

### Removed
- Unused `DEFAULT_STATE_SENSOR_TRIGGER_VALUE` constant.
- Unused `notify_service_failed` translation key (coordinator logs service errors directly).
- `_strip_empty_optionals` helper (no longer needed — empty optionals flow through naturally).

---

## [1.0.0] - 2026-04-06

### Added
- Initial release.
- Cycle detection via binary sensor (on → off) or state sensor (→ configurable completion value).
- Startup guard — sensor transitions from `unavailable` or `unknown` don't trigger false notifications.
- Repeating reminders until acknowledged, with configurable interval and maximum count.
- Snooze button on iOS/Android notifications.
- Arrival-deferred delivery — notifications wait until you get home.
- Persistent pending state — survives HA restarts.
- Dynamic person listener — only active while waiting, zero overhead when idle.
- Two-step config flow (entities, then timing) with reconfiguration and options flows.
- Single-instance guard.
- Diagnostics endpoint with redacted config.
- Full localization structure with help text for every config field.
