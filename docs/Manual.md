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
| SIMULATED STORM | The view is the superstorm card. The numbers are not a measurement. |

The four cards are the current solar-wind sample, the 3-day forecast
maximum Kp, the strongest flare in seven days, and the browser position.
Until geolocation answers, the position is Toronto. TEC on the demo sample
is unavailable.

The map is Leaflet on OpenStreetMap tiles, centered on that position. An amber pin marks the position. Leaflet's bundled marker image is not served by Next.js, so the pin is drawn by the page.

## Route

From and To are place names. Assess route asks Nominatim for coordinates and
OSRM for a driving path. Those two calls stay in the browser. The page draws
the full path and prints distance and duration.

The corridor score is not the banner score copied onto the line. The page
keeps at most 8 vertices from the OSRM line. The first vertex and the last
are always included. The other six are spaced evenly through the vertex
list, so the gaps follow how many points OSRM returned, not kilometers
along the road. A shorter line, one with 8 or fewer vertices, sends every
vertex. Those points go to `POST /route-score`.

Each sample uses the same score as the banner and the mail: nearest TEC
cell, geomagnetic-latitude band on the Kp term only, and no flare bonus on
the night side. Planetary Kp, the 3-day forecast, and any Earth-arrival CME
are the same at every sample. What can differ along the road is TEC, the
latitude band, and day or night. The server accepts at most 16 points. The
page sends 8.

The number in the sentence is the highest sample, not the average. A quiet
stretch does not pull that number down. The same sentence prints the lowest
and highest scores in the sample, and the advisory belongs to the highest
point. The line color follows that highest level: red at CRITICAL, teal at
LOW, amber otherwise.

If Nominatim or OSRM fails, no path is drawn. The sentence names the
failure and keeps the position score. If the path arrives and
`/route-score` does not, the path stays on the map and the sentence says
the local route score is unavailable. The superstorm step does not sample
the path. It colors an existing line from the storm card. The next step,
Simulate Route Risk, does sample the path.

## Simulated storm

![Simulated superstorm](images/ui-storm.png)

One button cycles through three views. The label is the next view.

1. Live. The button reads Simulate solar superstorm. The banner is the
   position score.
2. Superstorm. The first click replaces the snapshot with fixed storm
   numbers: Kp 8.3, forecast maximum Kp 9, an X4.2 flare, and an
   Earth-arrival CME. The banner becomes CRITICAL, 100/100, and the badge
   says SIMULATED STORM. The map center and zoom return to the Toronto
   region (zoom 9), From and To reset to Toronto, ON and Hamilton, ON, and
   any path already on the map is cleared. The pin turns red, and a dashed
   circle is drawn around Toronto. This step does not score route samples.
   The button
   then reads Simulate Route Risk. The capture above is this card.
3. Route risk. The next click returns the banner to the live position
   score and scores the current From and To fields. Those fields start as
   Toronto, ON and Hamilton, ON. The page draws that OSRM path, samples up
   to 8 vertices, and posts them to `/route-score` with `scenario` set to
   `storm`. The server scores those samples with the same superstorm
   numbers (Kp 8.3, forecast maximum Kp 9, flare X4.2, one Earth-arrival
   CME). The clock and the TEC grid stay live, so night side and local TEC
   still change the sample. The line color and the sentence use the
   highest of those hypothetical samples. The button then reads Back to Live.
4. The next click clears that path and returns to the live view.

None of these steps writes the database or sends mail.

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
