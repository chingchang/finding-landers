# The data

Everything is in `HiRISE/`. Credit for all of it: NASA/JPL/University of Arizona (PDS RDR V1.1,
hirise.lpl.arizona.edu/PDS/RDR/). The images are public domain; the credit line goes in every published output.

## What a strip is

HiRISE is the camera on the Mars Reconnaissance Orbiter. One observation is a long narrow "strip" of ground,
about 5 to 6 km wide and 10 to 40 km long, at 25 cm per pixel (some at 50 cm). Each strip here is two files:

- `<id>_RED.JP2`: the image, JPEG 2000, 0.5 to 2 GB, 16-bit samples holding 10-bit values (0 is "no data",
  1022 and 1023 are saturated). Read it in windows; never load a whole strip.
- `<id>_RED.LBL`: a text label with everything about the observation: pixel scale, map projection and its
  offsets (how to turn latitude and longitude into a pixel), the sun's direction and height (SUB_SOLAR_AZIMUTH,
  INCIDENCE_ANGLE), the season (SOLAR_LONGITUDE, "Ls"), the date, and the observation's title.

An id like `ESP_037145_1915` is mission phase, orbit number, and the target's latitude plus 180 times ten
(1915 means 11.5 N; 1035 means 76.5 S). `PSP_` strips are from 2006 to 2008, `ESP_` from 2008 on.

## What is on disk

`HiRISE/manifest.txt` is the list: one line per strip, `case  observation_id  url_base`. `HiRISE/strips/<case>/`
holds the files. 50 of the 66 strips are downloaded (about 47 GB); the `.done` marker files say which.

- `control_*` (16 strips, 12 sites): places where a lander or its pieces have already been found by people.
  These are the answer key; the Controls section below says which are for tuning and which are held out.
- `mpl_summer` (34 strips): the Mars Polar Lander search area at 76 S, all taken in southern summer (Ls 240 to
  345) when there is no seasonal frost. This is the open case. 32 of them carry the HiRISE title "Search for
  Mars Polar Lander": people have looked here before, by eye.
- `mpl_other` (7 strips, not downloaded): the same area in other seasons. Held for a later test, not the search.
- `mars3` (9 strips, not downloaded): a different site; not part of this work.

Two control strips are the wrong season and are being replaced: both Phoenix strips on disk (ESP_033724_2485,
ESP_068169_2485) are frost season at 68 N. The replacements are ESP_017716_2485 and ESP_053451_2485 (southern
hemisphere ids read the same way; these are northern summer). Until they are downloaded, Phoenix is not a usable
control.

Two more things to know about the controls: ESP_050177_1780 (Opportunity) has the sun 31 degrees from
overhead, so shadows are 2 px long and it cannot score a shadow-based test; and the MPL strip ESP_057965_1035
is a dune field, useful as a bed for false alarms rather than as search area.

## More data is allowed

What is on disk is a starting set, not a boundary. Fetching more public data is fine: more HiRISE dates of a
control site for persistence, the replacement Phoenix strips, CTX or other public imagery, anything with a
source and a credit line (`HiRISE/download_hirise.sh` and `manifest.txt` show the pattern; add new strips to the
manifest). Disk is the limit, not permission. The one restriction is the same everywhere: nothing from the
search area is ever used for tuning.

## Facts that shape the code

- Map coordinates in two strips of the same ground disagree by tens of metres (no ground control). Finding the
  same spot twice needs a local image registration, not just the label's projection.
- The MPL and Phoenix strips use a polar stereographic projection; the equatorial controls use equirectangular.
  Both come from the label and both must work.
- The valid area inside a strip is a slanted parallelogram; everything outside it is 0 and must be masked, not
  filled.
- Shadow length is height times tan(incidence); across the MPL strips tan runs from about 1.5 to 3.3.

## Controls: the answer key, and how it is kept honest

A control site is a place where a lander or its pieces have already been found by people in HiRISE images.
The pipeline is scored by whether it finds them without being told where they are.

### Three groups

- Tuning sites: used to build and tune the detector. Their answers are in `controls/tuning.json` and may be read
  by anyone and anything.
- Held-out sites (three): run once, at the end, with the detector frozen. Their answers are in `controls/heldout.json`,
  which agents never read and the scoring script reads only when a person runs the held-out evaluation.
- Final exam: Beagle 2 (three strips). Not opened until the held-out run is done. The published identification
  needed many images and super-resolution; a miss here is a legitimate result and is reported as one.

Which site is in which group is decided by a person before the first tuning run and never changed after.

| site | strips on disk | group | what is there |
|---|---|---|---|
| Schiaparelli | ESP_048041_1780, ESP_073625_1780 | tuning | crash scar, parachute, backshell, heat shield; two dates |
| Curiosity | ESP_030313_1755 | tuning | parachute, backshell, heat shield, descent stage, rover |
| Phoenix | ESP_017716_2485, ESP_053451_2485 (to download) | tuning | lander, backshell, parachute (fading), heat shield; polar; two dates |
| Viking 1 | ESP_046170_2025 | tuning | lander (bright, shadow) |
| Spirit | ESP_025815_1655 | tuning | lander platform, parachute, backshell, heat shield |
| Pathfinder | ESP_022038_1995 | tuning | lander, backshell, parachute, heat shield (50 cm/px) |
| Perseverance | ESP_068822_1985 | held out | parachute, backshell, heat shield, descent stage, rover |
| InSight | ESP_087360_1845 | held out | lander, backshell, parachute, heat shield |
| Zhurong | ESP_075625_2055 | held out | lander, parachute, backshell, heat shield, rover |
| Viking 2 | ESP_077167_2285 | spare | lander; not scored, not tuned on; a replacement if a tuning site fails |
| Opportunity | ESP_050177_1780 | spare | heat shield, parachute, backshell; sun too high for shadows |
| Beagle 2 | ESP_037145_1915, ESP_039308_1915, ESP_040363_1915 | final exam | lander, 1.5 m, partly deployed |

### What "sealed" means, honestly

Everyone can see which strip holds which site; the manifest says so and the names are famous. Anyone with a
browser can look up where Perseverance landed. So the held-out set is not a secret kept from the agent. It is
a procedure: the detector and its thresholds are frozen before those strips are run, no tuning ever uses them,
and `scripts/leakcheck.sh` greps the code, the prompts and the committed outputs for their coordinates so a
violation is caught rather than trusted not to happen. The number that comes out of the held-out run is only
worth something because of that procedure, which is why it is written down here.

### How the answers get made

`controls/sites.json` starts with published landing coordinates, good to about a kilometre. That is not an
answer key; a detector scored against it would be "right" anywhere within a kilometre. Before the first tuning
run, a person opens each tuning strip at the published position, finds the hardware by eye, and records the
pixel position of each piece. Those go into `controls/tuning.json` (readable) and `controls/heldout.json`
(sealed; the skeletons with the published positions already exist, the pixel positions are filled in by a person). The scoring script reports, per site and per piece, the rank of the true object in the candidate
list, which branch found it, and false alarms per square kilometre.
