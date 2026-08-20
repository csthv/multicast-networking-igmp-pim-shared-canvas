# Contributing

This repository is primarily an academic reproducibility package. Contributions should preserve the behavior and evidentiary value of the submitted work.

1. Do not edit files under `original_submission/`; those are preservation copies.
2. Make functional changes only under `src/`, `configs/`, `examples/`, or `docs/`.
3. Keep multicast defaults (`239.1.1.1`, UDP `5000`, TTL `16`) documented when changing them.
4. Run `python scripts/verify_repo.py` before committing.
5. For networking changes, document the tested topology, host IPs, RouterOS mode, and observed packet behavior.
6. Never commit credentials, private keys, or unrelated packet captures.
