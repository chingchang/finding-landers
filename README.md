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

The project incorporates Meta's models: the [Muse Spark series](https://dev.meta.ai/models/muse-spark),
[Muse Wonder](https://dev.meta.ai/models/muse-wonder), [Muse Image](https://dev.meta.ai/models/muse-image),
[Muse Voice Transcribe](https://dev.meta.ai/models/muse-voice-transcribe) and [SAM 3.1](https://dev.meta.ai/models/sam-3-1)
through the [Meta Model API](https://dev.meta.ai/products/meta-model-api), the open weights models
[Muse Glimmer](https://dev.meta.ai/models/muse-glimmer) and [Muse Spark Open](https://dev.meta.ai/models/muse-spark-open),
and the [Muse Code](https://dev.meta.ai/lp/muse-code) coding agent. In this pipeline: SAM 3.1 for segmentation,
Muse Wonder for vision, Muse Spark for review.

## License

Code: Apache-2.0 (see LICENSE). Data: public domain with the credit above. Model outputs: subject to Meta's
terms for the Meta Model API.
