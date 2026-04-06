# Wash Reminder

[![HACS Custom][hacs-badge]][hacs-url]
[![HA Version][ha-badge]][ha-url]
[![GitHub Release][release-badge]][release-url]
[![License][license-badge]](LICENSE)

Keeps reminding you to empty the washing machine until you actually do it. Works with [ha_washdata](https://github.com/3dg1luk43/ha_washdata) — no helpers, scripts, or automations needed.

If you're not home when the cycle finishes, the notification waits and fires when you walk through the door. If you open the machine door, reminders cancel automatically. Everything survives HA restarts.

> **Tip:** Turn off WashData's built-in cycle-end notification to avoid getting two alerts at once.

---

## Installation

### HACS

1. **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/napieraj/washreminder` as **Integration**
3. Download **Wash Reminder**, restart HA

### Manual

Copy `custom_components/washreminder/` to your config directory and restart.

---

## Setup

**Settings → Devices & Services → Add Integration → Wash Reminder**

### Step 1 — Entities

| Field | Description |
|---|---|
| Cycle completion sensor | `binary_sensor.washing_machine_running` (recommended) or a WashData state sensor |
| Completion state value | Leave blank for binary sensors. For state sensors, enter the done value, e.g. `Idle` |
| Person | Notifications are held until this person arrives home |
| Notification service | `notify.mobile_app_yourphone` — checked at setup time |
| Door sensor | Optional. A contact sensor on the machine door — opening it cancels all reminders |
| Invert door sensor | See [Door sensor polarity](#door-sensor-polarity) below |

### Step 2 — Timing

| Field | Default | Description |
|---|---|---|
| Snooze duration | 15 min | How long to wait after tapping Snooze |
| Repeat interval | 30 min | Time between automatic reminders if ignored |
| Max reminders | 10 | Stop after this many attempts (~5 h at default interval) |
| Arrival delay | 30 s | Grace period for your phone to reconnect to WiFi after arriving home. Set to 0 to notify immediately |

All timing settings can be changed later via **Configure** without reinstalling. Entity settings can be changed via **⋮ → Reconfigure**.

---

## How it works

```
🧺 Laundry Done
Time to empty the washing machine.

[ Snooze ]   [ Done ✓ ]
```

| What happens | What the integration does |
|---|---|
| You tap **Done ✓** | Notification cleared, reminders stop |
| You tap **Snooze** | Notification cleared, new reminder after the snooze duration |
| You ignore it | Another reminder at the repeat interval, with escalating text |
| You open the machine door | Everything cancelled — active reminders, pending state, delivery tasks |
| Cycle finishes while you're away | Saved to disk, notification sent when you get home |
| HA restarts while waiting | State restored, notification still sent on arrival |

Each reminder replaces the previous one on your phone — you'll never see a stack of duplicate notifications. Notifications break through Focus mode by default (iOS `time-sensitive`).

---

## Trigger modes

**Binary sensor** — fires when the sensor turns off. WashData debounces this, so brief power dips during a soak phase won't cause false alerts.

**State sensor** — fires when the sensor value changes to your configured completion state. Won't trigger on startup when the sensor goes from `unavailable` to `Idle`. Check the exact state string in **Developer Tools → States** — it's case-sensitive.

---

## Door sensor polarity

Most contact sensors in Home Assistant follow the convention where **"on" means open** and **"off" means closed**. The integration uses this by default — when the door sensor reports "on", it assumes the machine door has been opened and cancels any active reminders.

Some sensors work the other way around: they report **"off" when the door is open** and **"on" when closed**. If you find that reminders cancel when you *close* the door instead of when you *open* it, enable **Invert door sensor** in the entity settings. This tells the integration to listen for "off" instead of "on".

You can check how your sensor behaves in **Developer Tools → States** — open and close the door and watch which value appears.

---

## Troubleshooting

**Integration stuck on "Retrying setup"** — WashData hasn't finished loading yet. Reload Wash Reminder after WashData is ready.

**Notification buttons not working** — The Companion App needs notification permissions. On iOS: Settings → Notifications → Home Assistant.

**Reminders cancel at the wrong time** — Your door sensor may have inverted polarity. See [Door sensor polarity](#door-sensor-polarity).

**Debug logging:**

```yaml
logger:
  logs:
    custom_components.washreminder: debug
```

**Diagnostics:** Settings → Devices & Services → Wash Reminder → Download Diagnostics

---

## Requirements

- Home Assistant **2025.1.0+**
- [ha_washdata](https://github.com/3dg1luk43/ha_washdata) installed and configured
- HA Companion App (iOS or Android) with notification actions enabled

---

## Contributing

Issues and PRs welcome at [github.com/napieraj/washreminder](https://github.com/napieraj/washreminder).

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://hacs.xyz
[ha-badge]: https://img.shields.io/badge/HA-2025.1%2B-blue.svg
[ha-url]: https://www.home-assistant.io
[release-badge]: https://img.shields.io/github/v/release/napieraj/washreminder
[release-url]: https://github.com/napieraj/washreminder/releases
[license-badge]: https://img.shields.io/github/license/napieraj/washreminder
