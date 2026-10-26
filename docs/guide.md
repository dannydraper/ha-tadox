# Tado X — setup & recipes

Everything you need to make Home Assistant manage your tado° X heating: how
overrides really work, what each entity does, and copy-paste recipes for timed
overrides and a **weather-aware schedule**.

- [How tado overrides work (the mental model)](#how-tado-overrides-work)
- [What this integration gives you](#what-this-integration-gives-you)
- [Recipe: warm until a time, then resume](#recipe-warm-until-a-time)
- [Recipe: don't heat when it's mild out (weather cutoff)](#recipe-weather-cutoff)
- [Recipe: a weather-aware 9am–10pm schedule](#recipe-weather-aware-schedule)
- [Recipe: a one-tap boost button](#recipe-boost-button)
- [Letting Home Assistant manage the heating](#letting-ha-manage-the-heating)
- [Finding your entity IDs](#finding-your-entity-ids)
- [Rate limits](#rate-limits)

---

## How tado overrides work

tado always has a **schedule** running underneath. On top of it you can place an
**override**, and there are three kinds — the difference is only *when the
override ends*:

| Override | Ends when… | In Home Assistant |
|----------|------------|-------------------|
| **Manual** (no end time) | never — until you cancel it | the climate card's +/- and `heat`/`off` |
| **Timer** | after a set duration | the `tadox.set_climate_timer` action |
| *(none)* | you're following the schedule | `auto` mode |

Two things that trip people up:

- **A manual override survives schedule changes.** If you set 21 °C manually, the
  schedule hitting an "off" block at 10pm will *not* cancel it — it holds until
  you resume. (This is confirmed behaviour on the X hardware.) "Resume schedule"
  (`auto`) is what hands control back to the schedule.
- **The schedule is the floor; the override sits on top.** When no override is
  active, tado falls back to the schedule. So the schedule isn't something that
  "interrupts" you — it's what runs when you're not overriding.

Why this matters: the **weather cutoff only affects schedule-driven heating**
(see below). If you drive heating with *manual* overrides from an automation,
the cutoff can't gate them — a manual override always wins.

---

## What this integration gives you

**Per room** (device named after the room, e.g. *Living Room*):

| Entity | Example ID | What it is |
|--------|-----------|------------|
| Climate | `climate.living_room` | current/target temp, `heat`/`off`/`auto`, heating or idle |
| Humidity | `sensor.living_room_humidity` | relative humidity |
| Heating power | `sensor.living_room_heating_power` | tado's own duty-cycle % (not boiler telemetry) |
| Window | `binary_sensor.living_room_window` | open-window detection |
| Connectivity | `binary_sensor.living_room_connectivity` | device online (diagnostic) |
| Battery | `binary_sensor.living_room_battery` | low battery (diagnostic) |

**Per home** (device *tado° System*):

| Entity | Example ID | What it is |
|--------|-----------|------------|
| Weather cutoff | `switch.tado_system_weather_cutoff` | enable the "don't heat when mild" rule |
| Weather cutoff temperature | `number.tado_system_weather_cutoff_temperature` | the threshold (default 15 °C) |
| Weather cutoff active | `binary_sensor.tado_system_weather_cutoff_active` | on while it's suppressing heat |
| Outside temperature | `sensor.tado_system_outside_temperature` | tado's weather for your location |
| API requests remaining | `sensor.tado_system_api_requests_remaining` | today's quota (diagnostic) |

**Action:** `tadox.set_climate_timer` — a timed override (below).

> Entity IDs are examples. Confirm yours under **Developer Tools → States**;
> see [Finding your entity IDs](#finding-your-entity-ids).

---

## Recipe: warm until a time

The `tadox.set_climate_timer` action heats a room to a temperature **until a
clock time** or **for a duration**, then automatically resumes the schedule.
tado's cloud enforces the auto-resume, so it still happens even if Home
Assistant restarts.

Until a time of day (rolls over to tomorrow if the time has already passed):

```yaml
action: tadox.set_climate_timer
target:
  entity_id: climate.living_room
data:
  temperature: 21
  until: "00:00"        # warm until midnight
```

For a fixed duration:

```yaml
action: tadox.set_climate_timer
target:
  entity_id: climate.living_room
data:
  temperature: 21
  duration: "02:00:00"  # warm for two hours
```

Pass **either** `until` **or** `duration`, not both.

---

## Recipe: weather cutoff

"Don't let the heating come on when it's mild enough outside."

1. Turn on **`switch.tado_system_weather_cutoff`**.
2. Set **`number.tado_system_weather_cutoff_temperature`** (default 15 °C).

While the outside temperature is **at or above** the threshold, rooms that are
**following the schedule** are turned off; when it cools back below, they resume
automatically. **`binary_sensor.tado_system_weather_cutoff_active`** shows when
it's suppressing heat.

Key points:

- **Off by default** — nothing changes until you enable it.
- **A manual or timed override always wins.** The cutoff never reverts a change
  you made on the card or via `set_climate_timer` — it only gates heating that's
  coming from the *schedule*. (So to make it do anything, the room must be in
  `auto`.)
- It re-checks on **every poll**, so it's weather-aware all day, not just once.
- It uses the **current** outside temperature. To decide on the forecast
  instead, see the note in the next recipe.

---

## Recipe: weather-aware schedule

Goal: **heat 9am–10pm, but skip it whenever it's warm outside.**

The clean way is a plain time schedule **plus** the weather cutoff — *not* an
automation that sets temperatures (that would be a manual override and bypass
the cutoff).

### Option 1 — schedule in tado (simplest, has a fallback)

1. In the tado app, set the Living Room schedule: **ON 21 °C, 09:00–22:00**, OFF
   the rest of the day.
2. Leave `climate.living_room` in **`auto`**.
3. Turn on the **weather cutoff** (threshold 15 °C).

Result: heats 9am–10pm, suppressed whenever it's ≥15 °C out, re-checked
continuously. If Home Assistant is ever down, tado still runs the window on its
own.

### Option 2 — control the times from Home Assistant

Keep the tado schedule **flat** (e.g. 21 °C all day), weather cutoff **on**, and
let two automations open and close the window. The trick: at 9am **resume the
schedule** (so the room is schedule-driven and the cutoff can gate it) rather
than setting a temperature.

```yaml
# configuration.yaml  ->  automation: !include automations.yaml  (or the UI)
- alias: Heating window start (9am)
  triggers:
    - trigger: time
      at: "09:00:00"
  actions:
    - action: climate.set_hvac_mode     # resume schedule -> cutoff applies
      target:
        entity_id: climate.living_room
      data:
        hvac_mode: auto

- alias: Heating window end (10pm)
  triggers:
    - trigger: time
      at: "22:00:00"
  actions:
    - action: climate.turn_off
      target:
        entity_id: climate.living_room
```

Now the **times** live in HA, the **temperature** comes from the flat tado
schedule, and the **weather-awareness** is the cutoff — continuously, during the
window. Trade-off: if HA is down at 9am, nothing opens the window (Option 1 has
tado as a fallback).

### Deciding on the forecast instead of "right now"

The weather cutoff uses the current outside temperature. To decide on the
forecast high ("don't bother, it'll be 18 °C by noon"), gate the 9am automation
on a weather/forecast entity, e.g.:

```yaml
- alias: Heating window start (9am, forecast-aware)
  triggers:
    - trigger: time
      at: "09:00:00"
  conditions:
    - condition: numeric_state
      entity_id: sensor.todays_forecast_high   # your own forecast sensor
      below: 15
  actions:
    - action: climate.set_hvac_mode
      target:
        entity_id: climate.living_room
      data:
        hvac_mode: auto
```

(A forecast-high sensor can come from the Met Office / Open-Meteo integrations
or a template on a `weather.*` entity.)

---

## Recipe: boost button

A dashboard button that boosts to 21 °C for two hours, then auto-resumes:

```yaml
type: button
name: Boost 2h
icon: mdi:fire
tap_action:
  action: perform-action
  perform_action: tadox.set_climate_timer
  target:
    entity_id: climate.living_room
  data:
    temperature: 21
    duration: "02:00:00"
```

---

## Letting HA manage the heating

The one decision to make up front: **what happens when Home Assistant isn't
running?**

- **Keep tado's schedule as a safety net (recommended).** Set it to a sane
  baseline (your 9am–10pm window, or a low all-day floor like 16 °C). HA drives
  the smarts on top. If the Pi reboots or HA crashes, the house still holds the
  baseline. This is Option 1 above.
- **Make HA the sole brain.** Flatten the tado schedule to OFF/frost so tado
  never heats on its own, and let HA drive everything. Cleaner mental model, but
  if HA is down, nothing heats until it's back.

Either way, a **manual override always wins over the cutoff**, so you can always
grab control from the card and the weather rule won't fight you.

---

## Finding your entity IDs

The IDs in this guide are examples. To find yours:

- **Developer Tools → States**, and filter by `tado`, your room name, or
  `tado_system`.
- Or **Settings → Devices & services → Tado X → <device>** to list a device's
  entities.

Room entities are named after the room (`climate.living_room`); home-wide ones
live on the *tado° System* device (`switch.tado_system_weather_cutoff`, etc.).

---

## Rate limits

tado limits API requests per day (free accounts get a few hundred to ~1000).
This integration polls room state on your interval (default 5 min) and fetches
the heavier device + weather data only every sixth poll. Watch
`sensor.tado_system_api_requests_remaining`; if it runs low, raise the polling
interval under **Settings → Devices & services → Tado X → Configure**.

Every override, resume, and cutoff action also spends one request — so very
chatty automations eat into the budget.
