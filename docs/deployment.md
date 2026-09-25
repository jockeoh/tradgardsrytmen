# Configuration and private deployment

The default settings support local development. Copy values from `.env.example` into your shell or service environment as needed; Django does not automatically read that file.

## Optional integrations

Set `OPENAI_API_KEY` to enable care research. Saving a plant does not start research. Explicitly requesting new advice sends plant details, notes, garden profile and care history to the configured research service. Suggestions remain pending until reviewed. With no key, manual features continue to work. `TRADGARDSRYTMEN_OPENAI_MODEL` selects the model.

Web Push requires a secure browser context and permission on each device. Configure `TRADGARDSRYTMEN_VAPID_SUBJECT` with your own contact address. The application creates a private signing key in the data directory; never commit it. iPhone notifications require installation on the home screen.

## Data

`TRADGARDSRYTMEN_DB_PATH` selects the SQLite file and `TRADGARDSRYTMEN_DATA_DIR` holds runtime keys and backups. Keep both outside the checkout in production.

```sh
python manage.py backup_database
```

The backup command uses SQLite's backup API, checks database integrity and keeps fourteen days of backups. Test restores into a separate database.

For a separate local demo, choose an unused path before migrating and seeding:

```sh
export TRADGARDSRYTMEN_DB_PATH=/tmp/garden-demo.sqlite3
python manage.py migrate
python manage.py createsuperuser --username demo
python manage.py seed_demo --owner demo
```

The demo command requires an explicit existing owner. It never clears or overwrites an existing garden.

## Linux service

The included deployment scripts describe the original private installation and need a checkout path and Git owner appropriate to your host. Review them before use. They install systemd units, take a backup, apply migrations, collect static files and check the service before recording the deployed revision. They use fast-forward Git updates and reject a modified checkout.

The web service binds to `127.0.0.1:10443`; the Tailscale unit exposes it within the authenticated private network. Django login and garden membership protect the web application and both API generations. A private single-owner installation may use the explicitly created local owner while OIDC remains disabled. Public or external multi-user operation remains blocked until the chosen Auth0 EU tenant, decided token lifecycle and revocation flow have been configured and rehearsed.

Set a generated `TRADGARDSRYTMEN_SECRET_KEY`, disable debug, and configure the allowed host and trusted HTTPS origin for your installation. The development secret is rejected when debug is off. Keep the environment file readable only by the service administrator.

The bearer-token verifier is fail-closed unless `TRADGARDSRYTMEN_OIDC_ISSUER`,
`TRADGARDSRYTMEN_OIDC_AUDIENCE` and `TRADGARDSRYTMEN_OIDC_JWKS_URL` are all set.
It accepts signed RS256 access tokens with the configured audience and required scope;
identity matching uses issuer plus subject, never email. Automatic account provisioning is
off by default. Use `link_oidc_identity` to link an explicitly selected local account and
`revoke_oidc_identity` for immediate local revocation.

AI research and reminder delivery require external services and are not exercised against live accounts by the test suite. The annual overview loads the selected month and year, separating planned occurrences from recorded history.


## Care identity migration (local verification before deployment)

Back up before migrating. Migrations 0008–0010 add stable plant/moment/scope identities,
explicit one-off windows, advice classification and archival metadata. Existing rules
are marked for review rather than silently reclassified. Migration 0010 records explicit
identity refinements/merges so history and exclusions can follow the reviewed work.
Read endpoints never create tasks.

All maintenance commands require the intended garden's public UUID. Run
`python manage.py clean_care_content --garden UUID --report /path/to/inventory.json`
to inventory.
Run the same command with `--apply` only against the intended database: it takes a separate
SQLite backup with an integrity check, archives exact automatic duplicates and expired
open automatic occurrences, and creates review proposals for ambiguous existing rules.
Manual tasks, completed/skipped history and all notes are preserved. Running it again
is safe. The nightly materializer archives expired/duplicate occurrences and generates
only active planned rules; it never runs AI research.

Approvals require the current comparison token and an explicit explanation for unresolved
overlap candidates. SQLite write serialization and unique occurrence slots prevent repeated
approvals/need requests from creating duplicate work. Work identities are selected explicitly;
prose similarity identifies review candidates and never silently merges subgroups. Selecting an
existing work uses its exact scope. Refining a subgroup or merging an old identity is a separate,
audited choice whose source/target mapping is stored in the approval receipt.

Normal autodeploy takes the pre-migration backup, migrates, and then runs the idempotent cleanup
with an additional integrity-checked backup and a revision-specific report in the state directory.
It now fails closed unless `TRADGARDSRYTMEN_GARDEN_ID` identifies the intended garden.
On the first P2 transition, the schema migration may therefore finish before the script
stops at that guard. Create/link the verified owner and run `assign_legacy_garden` manually
against the backed-up installation, then set the printed UUID and rerun the deploy. This
staging is deliberate: the garden UUID does not exist before migration 0012 and must never
be guessed from account order.
If a process was started by an older installed deploy script, the missing revision report prevents
the next timer run from exiting early, so the transition completes safely on retry.
It does not run `replace_pending_research`; that command may call the research service and must
remain a separately authorized operation. After release, verify the deployed revision, health,
review queue and current/month views.

## Assigning existing private data

Migration 0012 deliberately leaves pre-existing domain rows unassigned. It never chooses the
first account or silently invents an owner. After backing up, preview the explicit assignment:

```sh
python manage.py create_private_owner --username admin
python manage.py assign_legacy_garden --owner USERNAME --garden-name "Min trädgård"
```

`create_private_owner` creates an active ordinary account with no usable password and no global
Django admin privileges. It prints a one-hour, single-use relative URL where the owner chooses
their own password; the operator never handles that password. Re-running is safe until a password
has been set. Once configured, the command refuses to reset an existing usable password.

Then repeat it with `--apply`. The command assigns the existing plant graph, settings and push
subscriptions atomically while preserving task, proposal, reminder and delivery history. Record
the printed garden UUID and use it for later scoped commands. Re-run the preview after application
to verify that no unassigned rows or cross-garden relations remain. Rehearse this against a restored
copy of the real database before any deployment.
