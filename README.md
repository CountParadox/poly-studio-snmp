# Poly Studio SNMP for Home Assistant

Monitors a Poly Studio video bar (developed against a Studio X70 on software 4.2.2) over
SNMP v2c, using the read-only `POLYCOM-ENDPOINT-MIB` (`1.3.6.1.4.1.13885.101`).

Optionally, if you give it the device's admin login, it also uses the Poly VideoOS REST API
for controls: mute, volume, dial, answer and end call, DTMF, camera presets, calendar,
digital signage, camera snapshots and reboot.

Local polling, no cloud, no extra Python packages.

## Requirements

- Home Assistant 2024.11 or later
- SNMP v2c enabled on the video bar, with a read-only community (port 161/UDP)

## Installation (HACS)

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add this repository's URL with type **Integration**.
3. Install **Poly Studio SNMP** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Poly Studio SNMP** and enter
   the host, port and community.

Manual install: copy `custom_components/poly_studio_snmp` into your `config/custom_components`
folder and restart.

## Entities

| Entity | Notes |
| --- | --- |
| In call, Sending content | Binary sensors |
| Active calls, Active conferences | Counts |
| Far site name / system | Unknown when idle |
| Call latency, jitter (receive / transmit) | Milliseconds |
| Packets lost (receive / transmit) | Cumulative per call |
| Packet loss (receive / transmit) | Percent |
| Video rate (receive / transmit), resolution, transmit frame rate | kbit/s |
| Status, hardware, SIP, SIP registration, camera, microphone, network interface, external integration | `disabled` / `ok` / `failed` |

Further status, per-stream jitter, codec and content-sharing sensors exist but are disabled
by default.

## REST controls (optional)

Enter the device's admin user name and password when adding the integration, or later via
**Reconfigure** on the integration entry. Leave the password empty for SNMP monitoring only.

| Entity | Type | REST endpoint |
| --- | --- | --- |
| Microphone mute | Switch | `/rest/audio/muted` |
| Camera mute | Switch | `/rest/video/local/mute` |
| Volume | Number (0-100) | `/rest/audio/volume` |
| End call | Button | `DELETE /rest/conferences/<id>` |
| Answer call | Button | `POST /rest/conferences/<id>/connections/<id>` (see note) |
| Join meeting | Button | `POST /rest/calendar/meetings/<id>` (current or next meeting) |
| Reboot | Button (disabled by default) | `/rest/system/reboot` |
| Digital signage | Switch | `/rest/system/mode/signage` |
| Camera preset | Select | `/rest/cameras/near/presets/<index>` |
| Calendar | Calendar | `/rest/calendar/meetings` |
| Camera snapshot | Camera (still image) | `/rest/cameras/snapshot/near_image_1.jpg` |
| Incoming call, USB device mode | Binary sensors | `/rest/conferences`, `/rest/system/mode/device` |
| Call state, Call address, Calendar service | Sensors | `/rest/conferences`, `/rest/calendar` |

Far-end and content snapshot cameras also exist, disabled by default.

### Actions

| Action | Fields |
| --- | --- |
| `poly_studio_snmp.dial` | `address`, optional `dial_type`, `rate`, `password` |
| `poly_studio_snmp.send_dtmf` | `digits` (0-9, `*`, `#`; a comma pauses one second) |
| `poly_studio_snmp.join_meeting` | optional `meeting_id` (defaults to the current or next meeting) |
| `poly_studio_snmp.recall_preset` | `preset` |
| `poly_studio_snmp.store_preset` | `preset` |

Every action takes an optional `device_id`; without it the action runs on every configured bar.

Example:

```yaml
action: poly_studio_snmp.dial
data:
  address: room42@example.com
```

**Answer call:** the reference guide exposes which connections are answerable but does not
document the answer request itself. The integration sends `{"action": "answer"}` to the
connection, which is unconfirmed; if it fails, enable auto-answer on the device instead.

The password is stored in Home Assistant's config entry. The device uses a self-signed
certificate, so TLS verification is disabled for these requests. If the login is rejected the
integration stops trying until it is reconfigured, to avoid locking the account.

## Notes and limitations

- The device refreshes its SNMP data roughly every 15 seconds; the integration polls every 30.
- The call table only exists during a call, so call sensors are `unknown` when idle.
- Only the first active call is reported.
- The MIB declares no units; the units above were inferred from observed values.
- SNMP v3 is not supported.
- The device exposes no room occupancy, people count or sleep state over SNMP or REST.
- The REST features were written from the Poly VideoOS REST API Reference Guide. The mute, volume
  and end call controls have been used on a Studio X70; dial, answer, DTMF, presets, calendar,
  signage and snapshots have not yet been tested against real hardware.
- The camera snapshot is a still image stored by the device, not a live stream.
