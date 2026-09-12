# python-library

The smallest useful policy. Two rules:

- `source-needs-tests`: a change to `src/pkg/module.py` must come with a change to some
  `tests/**/test_module*.py`, and the `unit` job on the head commit must be green. In local mode the
  CI requirement shows as pending, which is the honest answer before a push.
- `changelog`: a warning, not a block. It nags without stopping a hotfix.

Scenarios:

| file | expected |
|---|---|
| `missing-tests.json` | fail: `src/lib/parse.py` changed, no matching test |
| `pending-ci.json` | pending: tests present, CI still running |
| `complete.json` | pass |
