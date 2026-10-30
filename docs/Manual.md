# User interface

The site has a dashboard and a monthly newsletter. The dashboard shows the
current GPS risk, a map, a route check, and an email subscription. There is
no account and no login. The header links Dashboard and Newsletters.

The demo and simulated-storm screenshots were taken with `npm run dev` and
`NEXT_PUBLIC_API_BASE=https://address`. That host does not exist, so the
snapshot request fails, the badge stays on demo data, and the page prints
`TypeError: Failed to fetch`. With an empty `NEXT_PUBLIC_API_BASE` the same
demo numbers appear and Subscribe reports that nothing was stored. With a
real Modal URL the badge switches to LIVE when `GET /snapshot` succeeds.

## Live snapshot

![Dashboard on a live snapshot](images/ui-live.png)

This capture uses
`NEXT_PUBLIC_API_BASE=https://humble92--solar-gps-guardian-api.us-east.modal.run`.
`GET /snapshot` succeeded, so the badge is LIVE and the fetch error is gone.

The banner is MODERATE, 50/100. The browser score uses the larger of the
current Kp (0.67, from ACE) and the 3-day maximum (Kp 5). The forecast card
says a storm is expected. The strongest flare in seven days is C3.3, and the
TEC feed is available. DEGRADED MODE is absent because both DONKI and TEC
were present in this snapshot. The amber pin is still on Toronto.

## Demo data

![Dashboard on demo data](images/ui-demo.png)

The banner is the score the browser computes from the snapshot. In this
capture it is LOW, 30/100, because the built-in demo uses Kp 2 and a 3-day
maximum of Kp 3.

| Badge | Meaning |
|---|---|
| LOW, MODERATE, CRITICAL | Score bands: under 40, 40 to 69, 70 and above. |
| DEMO DATA | No live snapshot. The page is using the built-in sample. |
| LIVE | `GET /snapshot` returned a snapshot. |
| DEGRADED MODE | DONKI or the TEC feed was missing. The SWPC numbers are still shown. |
| SIMULATED STORM | The superstorm button is on. The numbers are not a measurement. |

The four cards are the current solar-wind sample, the 3-day forecast
maximum Kp, the strongest flare in seven days, and the browser position.
Until geolocation answers, the position is Toronto. TEC on the demo sample
is unavailable.

The map is Leaflet on OpenStreetMap tiles, centered on that position. An amber pin marks the position. Leaflet's bundled marker image is not served by Next.js, so the pin is drawn by the page.

## Route

From and To are place names. Assess route asks Nominatim for coordinates and
OSRM for a driving path, then draws the path and prints distance, duration,
and the same risk score. Those two services are called from the browser.
They do not go through the Python backend. If either call fails, the page
keeps the score and says the routing call failed.

## Simulated storm

![Simulated superstorm](images/ui-storm.png)

Simulate solar superstorm replaces the snapshot with fixed storm numbers:
Kp 8.3, forecast maximum Kp 9, an X4.2 flare, and an Earth-arrival CME.
The banner becomes CRITICAL, 100/100, and the badge says SIMULATED STORM.
The pin turns red, and a dashed circle is drawn around the position.
Back to live restores the snapshot or the demo sample and removes that circle.
This does not write the database and does not send mail.

## Subscribe

Email and region do not create an account. Subscribe geocodes the region
name and sends `POST /subscribe` with the email, latitude, longitude, and
region. The server stores that row and returns an unsubscribe token.

If the API base is empty, the button does not call a server. The message is
"Demo mode: no backend configured, subscription NOT stored." If the base is
set and the host is down, the message is a fetch error, as in the
screenshots.

A stored subscription receives one daily digest, subject "Solar wind daily
digest". An extra message, subject "Solar wind Critical Alarm", is sent only
when a 6-hour check sees CRITICAL. MODERATE, including a G1 forecast, stays
in the daily digest. Every message contains an unsubscribe link. The link is
checked with `UNSUBSCRIBE_SECRET`.

## Monthly newsletter

![September 2026 newsletter from the template](images/ui-newsletter.png)

Newsletters opens one issue. This capture is the September 2026 issue
written by the template, which is used when the language-model call fails.
The one-line take says the month is summarized by the numbers above.

The summary line is max Kp 5.0, minimum Dst -48 nT, 108 CMEs, 13 flares,
and 0 storms. Top events lists the first CME and flare rows. Next-month
watch points tell the reader to follow the daily SWPC 3-day forecast. The
bar chart is the daily maximum Kp from GFZ. The footer notes that OMNI was
unavailable for this run, and that Kyoto values are provisional.
