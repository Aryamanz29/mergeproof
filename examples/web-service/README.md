# web-service

Three areas, three kinds of proof:

- **Migrations** need a down migration in the tree, a `## Rollback` section in the description, and
  a note in the evidence block that the migration was rehearsed on staging or preprod.
- **UI changes** need a preview URL, before/after screenshot pairs, and a green end-to-end job.
- **Sensitive paths** need the `security-reviewed` label and a `/security-ok <sha7>` from one of two
  named people. Nobody else, and no bot, can satisfy that requirement.

Scenarios:

| file | expected |
|---|---|
| `migration-missing-rollback.json` | fail |
| `ui-change-complete.json` | pass |
| `auth-change-awaiting-security.json` | pending |
