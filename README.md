# Tado X for Home Assistant

A Home Assistant custom integration for **tado° X** heating hardware (the
Matter/Thread generation: Wireless Smart Thermostat X, Radiator Valve X,
Wireless Receiver X), talking to tado's `hops.tado.com` cloud API.

> **Why another tado integration?** Home Assistant's built-in `tado`
> integration doesn't support the X generation, and the native Matter path
> exposes only the setpoint (no schedules, no overrides-with-timers). This one
> is built for X from the ground up, with two specific goals:
>
> - **No daily re-authentication.** tado rotates the refresh token on every
>   refresh; this integration always persists the rotated token, so logins
>   last.
> - **Overrides that behave exactly as told** — no surprise revert to
>   automatic after a fixed time.

## Features

Per room:

- **Climate** entity — current temperature, target, `heat` / `off` / `auto`
  (follow schedule) modes, and a heating/idle action.
- **Timed overrides** — a `tadox.set_climate_timer` action: heat to a
  temperature until a time of day (e.g. midnight) or for a duration, then
  automatically resume the schedule.
- **Sensors** — humidity, heating power (tado's own duty-cycle %).
- **Binary sensors** — open window, connectivity, low battery.

Per home:

- **Weather cutoff** — a `switch` and a `number`: when enabled, heating is
  suppressed while the outside temperature is at or above the threshold (so a
  "21 °C all day" schedule won't fire the boiler on a mild day). A manual or
  timed override always wins, and a `binary_sensor` shows when it's active.
- **Outside temperature** (from tado's weather service).
- **API requests remaining** — a diagnostic sensor so you can watch your daily
  quota.

## Requirements

- Home Assistant 2024.11 or newer.
- A tado° X system and a tado account.
- No bridge, dongle, or local network setup — this uses the cloud API.

## Installation

### HACS (custom repository)

1. HACS → **⋮** → **Custom repositories**.
2. Add `https://github.com/dannydraper/ha-tadox`, category **Integration**.
3. Search **Tado X** in HACS → **Download**, then restart Home Assistant.

### Manual

Copy `custom_components/tadox` into your Home Assistant `config/custom_components/`
directory and restart.

## Setup

1. **Settings → Devices & services → Add Integration → Tado X.**
2. A progress screen shows a **URL and code**. Open the URL in a browser where
   you're logged into tado and approve.
   - If tado's page complains the request is *"missing a required parameter:
     client_id"*, open the URL with `&client_id=1bb50063-6b0c-4d11-bd99-387f4a91cc46`
     appended.
3. Once approved, the integration finishes automatically and your rooms appear.

## Using it

### Timed override ("warm until midnight, then resume")

Call the `tadox.set_climate_timer` action on a room's climate entity with a
target temperature and **either** an `until` time **or** a `duration`:

```yaml
action: tadox.set_climate_timer
target:
  entity_id: climate.living_room
data:
  temperature: 21
  until: "00:00"        # or, instead:  duration: "02:00:00"
```

When the timer ends, tado resumes the schedule on its own — so the auto-resume
still happens even if Home Assistant restarts in the meantime.

### Weather cutoff ("don't heat when it's mild out")

Turn on **Weather cutoff** and set **Weather cutoff temperature** (default
15 °C). While the outside temperature is at or above that value, rooms that are
following the schedule are turned off; when it cools below the threshold they
resume automatically. An explicit change (the card, or a timed override) always
takes priority, and the **Weather cutoff active** binary sensor shows when
suppression is in effect. It's off by default, so nothing changes until you
enable it.

## Options

**Settings → Devices & services → Tado X → Configure** lets you set the
**polling interval** (60–3600 s, default 300 s).

### A note on rate limits

tado limits API requests per day (free accounts get a few hundred to ~1000;
Auto-Assist subscribers get far more). To stay within budget, this integration
polls room state on your chosen interval and fetches the heavier device and
weather data only every sixth poll. Watch the **API requests remaining** sensor;
if it runs low, increase the polling interval.

## Roadmap

- Reading and editing smart schedules.
- Boost / resume-all buttons.

## Disclaimer

This is an unofficial, community integration. It uses tado's cloud API and is
not affiliated with or endorsed by tado°. Use at your own risk.

## Licence

MIT — see [LICENSE](LICENSE).
