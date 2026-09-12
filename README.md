# Kerbl IoT – Home Assistant Integration

[![CI](https://github.com/derjoerg/ha-kerbl-iot/actions/workflows/ci.yml/badge.svg)](https://github.com/derjoerg/ha-kerbl-iot/actions/workflows/ci.yml)
[![Validate](https://github.com/derjoerg/ha-kerbl-iot/actions/workflows/validate.yml/badge.svg)](https://github.com/derjoerg/ha-kerbl-iot/actions/workflows/validate.yml)
[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

Custom [Home Assistant](https://www.home-assistant.io/) integration for
[Kerbl IoT](https://www.kerbl-iot.com/) devices, built on top of the
[`kerbl-iot`](https://pypi.org/project/kerbl-iot/) Python client.

> **Status.** ✅ Step 1: project skeleton, domain, `manifest.json`,
> packaging, CI, test harness. ✅ Step 2: config flow (e-mail/password login,
> token-only storage) and the reauthentication flow. ✅ Step 3: push-driven
> `DataUpdateCoordinator`. ✅ Step 4: entity platforms, with the SmartCoop
> modelled as a root device plus linked sub-devices. ✅ Step 5: diagnostics.
> This README is kept as a living document and updated as each step lands.

## Account setup and reauthentication

Adding the integration asks once for your Kerbl IoT e-mail and password. On
success, only the resulting **access and refresh tokens** are stored in the
config entry – the password itself is discarded immediately and never
written to storage. On every restart, the stored tokens are restored onto
the API client and validated with one authenticated call.

If the stored session can no longer be used (`KerblAuthenticationError`,
e.g. the refresh token itself expired or was revoked), Home Assistant
automatically starts a **reauthentication flow**: it asks for the password
again for the same account and replaces the stored tokens with a fresh
pair. A transient connection problem instead schedules a normal setup
retry and does not trigger reauth.

Each Kerbl account is its own config entry, so multiple accounts can be
added side by side (duplicate accounts, matched case-insensitively by
e-mail, are rejected).

## Design goals

- **Multiple product lines.** `kerbl-iot` currently only models SmartCoop
  devices, but the integration is structured so future Kerbl product lines
  can be added as additional device types without redesigning the domain,
  config flow, or coordinator.
- **Multiple accounts.** Each Kerbl account is added as its own config
  entry; you can add as many Kerbl accounts as you like.
- **Devices with sub-devices.** A SmartCoop is modelled as one Home
  Assistant device, with its door, light, feeder, water heater and
  brightness sensor represented as linked sub-devices (`via_device_id`).
- **Push-driven, poll as fallback.** One `DataUpdateCoordinator` per config
  entry (= per account), fed primarily by the `kerbl-iot` Socket.IO push
  callbacks; `update_interval` (15–20 minutes) exists only as a
  self-healing fallback poll, not the primary refresh mechanism.
- **Core-grade quality bar in a HACS custom repo.** Strict `ruff` + `mypy`,
  `hassfest` and `hacs/action` validation, and tests with
  [`pytest-homeassistant-custom-component`](https://pypi.org/project/pytest-homeassistant-custom-component/)
  plus [`syrupy`](https://pypi.org/project/syrupy/) snapshot tests from the
  first commit – even though this integration is not (yet) intended for
  Home Assistant Core.

## Entity model (SmartCoop)

Every SmartCoop is one Home Assistant device (the root device, carrying its
firmware version as a device property, not a separate entity) plus five
linked sub-devices – one per physical component – each shown as its own
device page and linked back to the root device via `via_device_id`. The
coordinator pre-registers and links every device before any entity platform
runs (`async_update_device(..., via_device_id=...)`, a long-stable API),
rather than an entity linking itself through `device_info` – the newer
`via_device_id` key on entities' own `DeviceInfo` isn't consistently
available yet across Home Assistant releases.

| Device            | Entity                                    | Platform        |
| ----------------- | ------------------------------------------ | --------------- |
| SmartCoop (root)  | Air temperature                           | `sensor`        |
| SmartCoop (root)  | Errors (+ active errors attribute)        | `binary_sensor` |
| SmartCoop (root)  | Online                                     | `binary_sensor` |
| SmartCoop (root)  | Acknowledge errors                        | `button`        |
| Door              | Door                                      | `cover`         |
| Door              | Door state                                | `sensor`        |
| Door              | Door closes in                            | `sensor`        |
| Light             | Light (on/off)                            | `light`         |
| Light             | Dim value (0–100)                         | `sensor`        |
| Feeder            | Trigger feeding                           | `button`        |
| Feeder            | Feeding in progress                       | `binary_sensor` |
| Feeder            | Feed empty                                | `binary_sensor` |
| Feeder            | Feeding locked                            | `binary_sensor` |
| Water heater      | Water temperature                         | `sensor`        |
| Water heater      | Water sensor                              | `binary_sensor` |
| Brightness        | Brightness (0–100)                        | `sensor`        |
| Brightness        | External brightness sensor connected      | `binary_sensor` |

A SmartCoop that reports no door (`hasNoDoor`) gets no Door device or door
entities at all.

## Installation (HACS custom repository)

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/derjoerg/ha-kerbl-iot` with category
   **Integration**.
3. Install **Kerbl IoT**, restart Home Assistant, then add the integration
   via **Settings → Devices & services → Add integration** and sign in with
   your Kerbl IoT e-mail and password.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt

ruff check .
ruff format --check .
mypy custom_components
pytest
```

Snapshot tests use `syrupy`; after an intentional behaviour change, refresh
snapshots with:

```bash
pytest --snapshot-update
```

Review the resulting diff under `tests/__snapshots__/` before committing.

## Localization

English and German are supported (`custom_components/kerbl_iot/translations/`).

## License

MIT, see [`LICENSE`](LICENSE).
