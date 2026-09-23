# MZWiK Myślenice (eBOK) — Home Assistant integration

Home Assistant integration for water-meter data from the **MZWiK Myślenice**
utility's eBOK portal (`portal.mzwikmyslenice.com.pl`). It logs in to your own
account, lists your water meters, and brings their readings and consumption into
Home Assistant — including a history backfill into the Energy/Water dashboard.

Meters at MZWiK are read manually every few months, so the portal only knows a
consumption figure per reading period. This integration spreads each period's
consumption evenly across its days — e.g. 30 m³ over 10 days becomes 3 m³/day —
so the dashboard shows a sensible daily series instead of one giant spike on
reading day.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add this repository's URL, category "Integration"
3. Install "MZWiK Myślenice (eBOK)", then restart Home Assistant

### Manual

Copy `custom_components/mzwik_myslenice/` into your Home Assistant
`<config>/custom_components/` directory and restart.

## Configuration

Settings → Devices & Services → Add Integration → **MZWiK Myślenice (eBOK)**.
Enter your eBOK **client number** (Numer Odbiorcy Usług, used as the login) and
**password**, then pick which meters to track.

Credentials are stored only in your own Home Assistant config entry and are used
solely to log in to your account. The portal is polled once a day — readings
change at most quarterly, so there is no benefit to polling more often, and it
keeps load on the utility negligible.

## Entities

Per selected meter:

| Entity | Unit | Notes |
| --- | --- | --- |
| Meter reading | m³ | current cumulative dial value |
| Last period consumption | m³ | consumption booked at the last reading |
| Average daily consumption | m³/d | as reported by the portal |

## Consumption history

On first setup the integration backfills a **separate statistic**
(`mzwik_myslenice:water_<serial>`) with averaged daily consumption, so the Energy
dashboard's Water section can show history. Add it under Settings → Dashboards →
Energy → Water consumption.

Because the sum is built from per-period consumption (not the dial value), a
physical meter swap — which resets the dial — does not corrupt the history.

Re-run the backfill anytime with the `mzwik_myslenice.import_history` service; an
update that changes the import also re-imports itself on the next restart.

## Costs

The portal exposes only invoice totals, not per-m³ prices, so unit prices are
entered manually under the integration's **Configure** dialog (water price and
sewage price in PLN/m³, plus which meters include sewage — a garden meter is
usually water-only). A cost statistic (`mzwik_myslenice:cost_<serial>`) is then
built per meter; attach it as the cost of the matching water source in the Energy
dashboard. Changing the prices rebuilds the cost history automatically.

## Requirements

Home Assistant 2025.8.0 or newer.

## Notes

- All access is read-only; the integration never submits anything to the portal.
- This is an unofficial integration, not affiliated with or endorsed by MZWiK
  Myślenice. Use it with your own account and check that automated access is
  acceptable under the portal's current terms of use.
