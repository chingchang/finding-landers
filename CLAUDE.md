# Finding Landers

A search of public Mars orbital imagery for spacecraft that never called home.

The reader of every result is a planetary scientist who has spent years on these images and will check each
claim against the pixels. Write the code, the tests and the words for that reader. Published results in this
field are retracted for a single unearned claim, and the work here is judged the same way.

## Read first

- docs/data.md: what the images are, what is on disk, more data you may fetch, and the control sites (which
  are for tuning, which are held out, and how that is kept honest).

## What done means

The pipeline finds the hardware at every control site (places where a lander or its pieces are already known
to be) without being told where it is, with few enough false alarms that a person can check the list by hand.
Write the script that prints that score early, and keep it honest: it is the number the whole project is judged
on. Until it exists, a change is done when its tests pass.

## Lines that do not move

Each one is a condition of the project, is irreversible, or would invalidate the result. Everything else is your call.

- The model work uses Meta's models through the Meta Model API (SAM 3.1 for segmentation, Muse Wonder for
  vision, Muse Spark for review; the open weights Muse Glimmer or Muse Spark Open where they fit). This is a
  condition of the project, not a preference; README.md lists the models.
- The API key comes from the environment, never from code, prompts, logs or commits. The repo is public.
- Nothing that says where an image is from (image id, coordinates, date, file name) goes into a model prompt or
  into a committed result. The control sites are famous; a model that recognises one proves nothing.
- Results are described as candidate, needs second look, likely natural, or not assessed. Never found,
  discovered, confirmed or proven. One claim we cannot defend costs the whole entry.
- A result becomes a candidate only by passing the physical tests and being seen on two dates. A model's
  opinion can lower a result, never raise it.
- The pass/fail numbers, the list of control sites and the scoring script change only by a person. Propose a
  change in a file and stop; do not edit them yourself. Otherwise the test drifts toward the answer.
- Some control sites are held out for one final blind run. Never read that list, and never tune on the search
  area itself.
- Every model call is counted against a hard cap, and paid model calls run only when a person asked for them in
  this session.
- Every number in a document is copied from a results file the code produced, with the file named, so anyone can
  rerun the code and get the same number. No number is typed from memory or from a chat.

## Room to play

`experiments/` is yours: no review, no gate. Keep what moves the score, write one line in `docs/experiments.md`
for what did not, and move winners into the main package through a normal change.

## Tell me

End each piece of work with what you did, what you decided and why, and what you would do next, in a short
report file next to the work.
