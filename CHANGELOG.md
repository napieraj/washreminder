# Changelog

All notable changes to Wash Reminder will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.4.0] - 2026-04-06

### Added

- **WashData event trigger mode** — listens for `ha_washdata_cycle_ended` events from the [ha_washdata](https://github.com/3dg1luk43/ha_washdata) integration instead of watching a sensor entity. Trigger entity is now optional when using this mode. *(Recommended for ha_washdata users.)*
- **iOS notification action icons** — SF Symbols icons on Snooze (`clock.arrow.circlepath`) and Done (`checkmark.circle.fill`) notification action buttons.
- **iOS Focus mode override toggle** — option to disable the `time-sensitive` interruption level for users who don't want notifications to break through Focus mode.
- **Notify service compatibility** — support for notify services without entity registry entries (e.g. legacy `notify.mobile_app_*` services).

### Fixed

- Notify entity selector not showing iOS mobile app targets.
- HACS zip file creation producing a double-nested directory structure.
- Manifest version preventing integration from appearing in HA discovery.

### Changed

- Release workflow now derives the version from the git tag instead of `manifest.json`.
- Added setup screenshots and updated README documentation.

---

## [1.2.0b1] - 2026-04-06

### Fixed

- **Hassfest** — removed `homeassistant` key from `manifest.json` (no longer allowed by hassfest for custom integrations; minimum version is enforced via `hacs.json`).
- **Hassfest** — moved notification text out of `strings.json` / `translations/en.json` into a dedicated `translations/notify_en.json` file (hassfest rejects the unrecognised `notify` top-level key).
- **Hassfest** — sorted `manifest.json` keys alphabetically after `domain` / `name` as required by hassfest.

---

## [1.2.0b0] - 2026-04-06

Pre-release (HACS: enable **Show beta versions** for this repository). Tag **`v1.2.0b0`** — stable **`1.2.0`** will follow after beta feedback.

### Added

- Multi-step config and reconfigure flows: completion state only for state sensors; door invert only when a door sensor is selected; **notify.*** entities only for the notification target (with entity + service validation).
- **Pending notification** binary sensor, plus diagnostic **Activity** and **Runtime** sensors; coordinator listener bus pushes state updates.
- **`icons.json`** — MDI icons for the new entities (`default` / `state` schema per Home Assistant icon translations); English `entity` strings for names and sensor states.

### Changed

- Minimum Home Assistant **2026.1.0** (HACS metadata uses **2026.1.0b0** so Home Assistant beta installs satisfy the checker).
- README: badges, my.home-assistant.io link, wizard + entity documentation.
- CI: **Hassfest** job alongside HACS validation.

---

## [1.1.2] - 2026-04-06

### Fixed

- **HACS / branding** — RGBA `brand/icon.png` with transparency, plus root-level `icon.png` fallback for validators and the integration card (see commit `fix(brand): RGBA icon with transparency, add root-level fallback`).

### Changed

- Version bump to **1.1.2** (manifest).

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