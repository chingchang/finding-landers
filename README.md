# Finding Landers

A search of public Mars orbital imagery for spacecraft that never called home.

Everything here was written between October 27 and November 4, 2026.

Every result is graded candidate, needs second look, likely natural, or not assessed, from physical tests
that run as code against published thresholds.

## Data

HiRISE images from the Mars Reconnaissance Orbiter, PDS RDR V1.1, from hirise.lpl.arizona.edu/PDS/RDR/.
Credit: NASA/JPL/University of Arizona. The images are public domain; they are not stored in this repo (see
`docs/data.md` for what is on disk and how it is used). Any image or crop published from this work carries the
same credit line.

## Models

The pipeline calls three of Meta's models through the [Meta Model API](https://dev.meta.ai/products/meta-model-api):

- [SAM 3.1](https://dev.meta.ai/models/sam-3-1) outlines each candidate inside a box around it, so its size and
  shape can be measured and tested.
- [Muse Wonder](https://dev.meta.ai/models/muse-wonder) looks at a blind crop of each candidate and votes on
  whether it looks like hardware or natural ground. Its vote can lower a grade, never raise one.
- [Muse Spark](https://dev.meta.ai/models/muse-spark) reviews each strip's evidence through a fixed set of tools
  and keeps or lowers each grade, citing the evidence it used.

## License

Code: Apache-2.0 (see LICENSE). Data: public domain with the credit above. Model outputs: subject to Meta's
terms for the Meta Model API.
