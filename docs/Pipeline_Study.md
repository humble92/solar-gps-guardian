# Pipeline study and the risk score

This document covers what the score measures and why: the inputs, their
physics, their limits, and the study that chose the data pipeline. How the
service runs (Modal, the snapshot, the API) is in
[Tech_Stack.md](Tech_Stack.md).

## Risk score

`backend/risk.py` owns the score. The weights are constants in that file:

| Input | Points |
|---|---|
| Each Kp point, using the largest of SWPC current Kp, the SWPC 3-day maximum, and the GFZ Kp nowcast | 10 |
| GOES X-ray flux at snapshot time is M class (1e-5 W/m2 or more) | 15 |
| GOES X-ray flux at snapshot time is X class (1e-4 W/m2 or more) | 25 |
| A WSA-Enlil Earth shock arrival (DONKI) predicted between 72 h ahead and 24 h ago | 20 |
| Vertical TEC of the nearest GloTEC cell at or above 50 TECU (large-delay level) | 10 |
| Local TEC at least 10 TECU above or below its 30-day median (GloTEC anomaly, observed cells only) | 10 |

The total is clamped to 0..100. Under 40 is LOW, under 70 is MODERATE, 70
and above is CRITICAL. Missing inputs score 0, LOW. Solar-wind speed and Bz
are stored for the sentence and are not part of the sum.

### Kp

The Kp term uses the largest of SWPC current Kp, the SWPC 3-day forecast
maximum, and the GFZ Kp nowcast. GFZ is a cross-check: on a mismatch the
larger value is scored (conservative), and a gap of 1 or more between SWPC
and GFZ is named in the sentence. Kyoto Dst is fetched for the record and
the newsletter, and is not scored.

### Flares

The flare term is the GOES X-ray flux at snapshot time. A flare's X-rays
disturb the sunlit ionosphere only while the flare lasts (minutes to about
two hours), so a flare from days ago is not a risk now. The strongest flare
of the last 7 days is shown on a card and in the sentence, and it is not
scored. The flux is the latest 0.1-0.8 nm sample from the GOES 6-hour
file. GOES writes one sample a minute, and the newest one was 4 to 5
minutes old when checked on 2026-10-31. The snapshot is refreshed every 5
minutes, so the flare term is about 5 to 10 minutes old when a score uses
it.

### CMEs

The CME points come from DONKI's WSA-Enlil runs of the last 7 days: the
predicted Earth shock arrival (`estimatedShockArrivalTime`) counts from 72
hours before it to 24 hours after it. 72 hours matches the 3-day forecast;
24 hours covers the storm the CME drives. An arrival that passed days ago
no longer adds points.

### Location

After that sum, location changes four things.

Latitude. The Kp term is multiplied by a geomagnetic-latitude band: 1.0 in
the high band, 0.8 from 30 degrees up to the high band, and 0.6 below 30.
The bands are steps, not a smooth curve. Magnetic disturbance peaks in the
auroral zone (about 60 to 70 degrees), not at the pole, and that zone moves
toward the equator as Kp rises. So the high band starts at
min(55, 66 - 1.8 x Kp) degrees, using the same Kp as the score. The line is
a rough fit (about 66 degrees at Kp 0, about 50 at Kp 9), and it only widens
the band above Kp 6.1: Kp 7 starts it at 53.4, Kp 8 at 51.6, Kp 9 at 49.8.
The polar cap above the auroral zone keeps the full weight. The pole used
for that band is 80.6 N, 72.6 W.

Auroral oval. A place is also in the high band when the SWPC OVATION
nowcast puts it under the auroral oval (aurora value 10 or more out of 100
in its 1-degree cell). OVATION is a 30 to 90 minute forecast driven by the
solar wind, so it catches the oval bulging toward the equator on the night
side during a substorm, which Kp cannot place. Without an OVATION grid the
Kp rule alone decides.

Day and night. Local solar time comes from longitude and `fetched_at`.
Outside 06:00 to 18:00 the flare points are omitted, because a flare's
X-rays never reach the night side. The night side is hit later by the CME
and the geomagnetic storm, which the Kp and CME terms score everywhere.

TEC. The two TEC terms below use the nearest GloTEC cell.

### TEC level (50 TECU)

The 50 TECU term measures how much ionosphere is overhead, not whether a
storm is going on. 1 TECU is about 0.16 m of GPS L1 delay, so 50 TECU is
about 8 m straight up and more on low-elevation paths. A single-frequency
receiver's broadcast model removes only part of that, so a larger TEC
leaves a larger error. The level is a judgment, not a published standard.
At mid latitudes TEC usually passes 50 only in a storm. Within about 15 to
20 degrees of the magnetic equator it passes 50 on many afternoons near
solar maximum (the grid peaked at 80 TECU on 2026-10-31), so those places
get these 10 points on ordinary days. The storm signal is the deviation
term below; both can apply, for 20 points.

### TEC deviation (30-day median)

The TEC-deviation points use the GloTEC `anomaly` field, which SWPC defines
as the deviation from the 30-day median. They count a depletion as well as
an enhancement, because either one is delay a receiver's model does not
expect (10 TECU is about 1.6 m on L1). The field is used only where the
cell's `quality_flag` is above 0. SWPC describes that flag as the number of
observations ingested, and on 2026-10-31 it was 5 over Toronto, Iowa,
Berlin and Tokyo and 0 over open ocean and the Sahara. A 0 cell's anomaly
is model output, so it is ignored.

### TEC age

GloTEC writes a tile every 10 minutes, with no gaps over the 31 days the
directory keeps (checked 2026-10-31), but each tile appears about 1.3 hours
after its time tag. So the TEC terms describe the sky of about 1.5 hours
ago. Both TEC terms are skipped when the stored grid's tile time is more
than 3 hours older than the snapshot (`TEC_MAX_AGE_H`). The sentence always
names the tile time and its age, for example "Local TEC 28 TECU (GloTEC
21:35 UTC, 1.4 h old)" or "TEC terms skipped: grid older than 3 h".

## What the score does not model

- Night-side substorms are covered only as far as OVATION places the oval.
  Their timing inside a 3-hour Kp interval, and anything faster than the
  OVATION update, is not modeled.
- Traveling ionospheric disturbances are covered only at large scale. The
  GloTEC anomaly is a 10-minute map on a 5 by 2.5 degree grid, so it sees a
  storm-time TEC rise or drop, including large waves, but not medium-scale
  TIDs that are tens to hundreds of kilometers across and pass in minutes.
- Post-sunset scintillation near the magnetic equator, within about 20
  degrees of it, mostly between 19:00 and 01:00 local time. This is a known
  GPS hotspot. No feed in the pipeline measures it, and the score does not
  guess it.
- Day and night use local solar time, 06:00 to 18:00, not the real
  terminator. Near the poles in winter the Sun can stay down at noon, and
  in summer up at midnight, so the flare rule is approximate there.
- Solar proton events. Protons enter over both polar caps, day and night,
  and mainly black out HF radio there (polar cap absorption). GPS is
  affected much less. The GOES proton feed is open but not read.

## Why this pipeline

Six candidates were scored on 2026-10-26. Weights: GPS fidelity 25%, lead
time 20%, location and route specificity 15%, behavior when a feed is down
15%, implementation simplicity 10%, cost and keys 10%, explainability 5%.

| ID | Idea | Weighted score |
|---|---|---|
| P1 | SWPC indices only | 3.50 |
| P2 | P1 plus TEC | 3.65 |
| P3 | P1 plus DONKI | 3.10 |
| P4 | SWPC, DONKI, TEC, and the Dst/GFZ cross-check | 4.60 |
| P5 | The model assigns the number | 2.35 |
| P6 | OMNI science archive | 2.65 |

The table is the study as scored on 2026-10-26 and is not re-scored.

P4 is the live path. P2 is the fallback if DONKI stays unreachable. P1 is
the floor when several feeds are down. P5 was rejected because a model must
not invent the score. P6 stays off the live path because the archive is
delayed and the GSFC download is blocked from some networks. The full grid
is [pipeline-study-scorecard.csv](../pipeline-study-scorecard.csv).

### Changes after the study (2026-10-31)

- GFZ cross-check. P4 lists it, but until this date GFZ Kp and Kyoto Dst
  were only stored in the snapshot. Now the Kp term uses the largest of
  SWPC current Kp, the SWPC 3-day maximum, and the GFZ nowcast
  (conservative on mismatch), and a gap of 1 or more between SWPC and GFZ
  is named in the sentence. Dst stays unscored: it is fetched for the
  record and the newsletter.
- DONKI. The CCMC host takes no API key; the scorecard's P3 note "needs a
  key" was wrong. The CME term read `impactList`, which never holds Earth,
  so it never fired. It now reads `estimatedShockArrivalTime` and counts an
  arrival from 72 hours ahead to 24 hours after it.
- New inputs: the SWPC OVATION auroral-oval nowcast (latitude weight) and
  the GloTEC deviation from the 30-day median (10 points).
- Flare term: the GOES X-ray flux at snapshot time instead of the 7-day
  strongest flare, which is now shown only.
- TEC: a 3-hour age limit on the grid, with the age printed in the
  sentence.
- Feed handling (secondary GOES satellite, GloTEC directory listing, Kyoto
  month start), the 5-minute ingest, and the volume reload are described in
  [Tech_Stack.md](Tech_Stack.md).
