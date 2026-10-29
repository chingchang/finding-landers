"""The model layer: SAM 3.1, Muse Wonder and Muse Spark through one interface (docs/models.md).

Everything here runs blind. The leak guard (``leak``) refuses any request that says where an image is
from; the ledger (``ledger``) counts every call against a hard cap; the backends (``backend``) are ``fake``
(deterministic, in-process), ``recorded`` (replays saved results by request hash), ``dry-run`` (writes the
request it would send) and ``real`` (the SDK, constructed only when a person exported the key and
``LANDERS_REAL_CALLS=1``). No model here can raise a grade.
"""
