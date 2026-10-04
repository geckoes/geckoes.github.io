# Portfolio Status

The site stays static. GitHub Actions reads Engineering Portfolio and public
repository milestones, validates all configured projects, and generates
`_site/projects-status.json`. The browser fetches only that same-origin file
and renders it with `projects-status.js`; it never calls GitHub's API.

## Authentication and first deployment

For a **personal** GitHub Project, create a **personal access token (classic)**
as `geckoes`, with **only `read:project`**, and an expiration date. Store it in
this repository's Actions secret **`PORTFOLIO_READ_TOKEN`**. Do not put the token
in source code, JSON, browser code, or command-line arguments.

GitHub currently lists user-owned Projects as unsupported by fine-grained PATs.
The workflow's `GITHUB_TOKEN` cannot access Projects. The collector reads public
repository milestones without authentication, so no `repo`, `public_repo`,
`project` (write), or `workflow` scope is needed. Private repositories are not
supported by this minimal configuration.

Official references, checked 2026-10-04:

- [Projects API authentication (`read:project` for queries)](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects)
- [Fine-grained PAT limitations (user-owned Projects)](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [GITHUB_TOKEN cannot access Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/automating-projects-using-actions)
- [Public milestones API and pagination](https://docs.github.com/en/rest/issues/milestones)
- [Deploying Pages artifacts and required permissions](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

Before enabling deployment, run collection successfully with the dedicated PAT
and confirm the live Project fields match the configuration. In repository
Settings → Pages, select **GitHub Actions** as the publishing source. Keep the
existing custom domain (`filippotaiuti.dev`) and HTTPS configuration. No settings
are changed by the local implementation.

## Source contract

Only the existing **Project**, **Target**, **Priority**, and **Phase** fields are
read. They may be text or single-select fields. No fields or Project items are
created or modified. The collector discovers the open personal Project by the
exact title `Engineering Portfolio`, paginating the user's Projects and items;
the Project must be unique and visible to the token.

`portfolio-status.config.json` maps `Project` field values to repositories and
explicit target membership. Aliases accept the human-readable project name or
repository slug. Change these mappings if the live Project uses different
values; there is no fallback to issue titles or hardcoded metadata.

Metadata (`Project`, `Target`, `Priority`, `Phase`) is always read from GitHub.
An empty Target is allowed in discovery. Exactly one active item per configured
project and one card per priority are required. Archived items are ignored.
Supported phases are `DISCOVERY` and `DEVELOPMENT`; additional lifecycle phases
need an explicit contract change.

Expected Run has no configured repository link: the public URL
`geckoes/expected-run` returned 404 during inspection. Add a repository only
when its public identity is confirmed. Discovery does not require a repository
or milestone API calls.

## Target milestones and current milestone

Temperature Monitor's `v1.0 Portfolio Release` explicitly includes **M00–M07**,
in that order. Each identifier matches a milestone title beginning with the
identifier followed by whitespace or the end of the title. M02 matches
`M02 — API Robustness`, but not M020. Full titles can change after the identifier.
Numeric milestone IDs/numbers are never used for matching or configuration;
the API-provided milestone URL is used only as a navigation link.

Every configured identifier must match exactly one repository milestone. Missing
or ambiguous matches fail collection. Unrelated milestones never affect the
denominator. A new development target must have explicit membership configured;
there is no implicit "all milestones" fallback.

Progress is `round(100 × closed target milestones / all target milestones)`,
with half percentages rounded up. Current milestone is the **first open milestone
in configuration order**, resolving title/link from the repository API. When all
are closed, progress is 100% and current milestone is null. Discovery always has
null progress/current milestone, so it never renders 0% or a progress bar.

Acceptance snapshot:

| Project | Priority | Phase | Target | Progress | Current |
| --- | --- | --- | --- | --- | --- |
| Temperature Monitor | PRIMARY | DEVELOPMENT | v1.0 Portfolio Release | 25% (2/8) | M02 — API Robustness |
| Expected Run | NEXT | DISCOVERY | MVP | absent | absent |
| Air Quality Intelligence | INCUBATING | DISCOVERY | from Project, if present | absent | absent |

Milestone titles/states were verified via the public API on 2026-10-04. Project
metadata in the test fixtures is the user's acceptance specification, **not a
verified live Project capture**. The collector has no fixture mode and the
workflow never publishes test fixtures.

## Output and failures

The JSON has `schema_version`, UTC `updated_at`, a Project `source` title/URL,
and priority-ordered `projects`. Each project contains metadata,
`repository_url`, nullable `progress` (`closed`, `total`, `percent`), and nullable
`current_milestone` (`title`, `url`). Only this public allowlist is serialized.

All API results are validated before an atomic JSON replacement. HTTP/network
errors, GraphQL errors (including partial results), missing metadata, unexpected
priorities/phases, unknown targets and ambiguous/missing milestones fail with a
nonzero exit. Neither the output nor the previous Pages deployment is replaced.

The token is used only in the GraphQL Authorization header. Public output uses
an explicit field allowlist, and collection refuses to write JSON containing the
token even if an API metadata field unexpectedly reflects it. Error messages
redact the exact token before logging. Regression tests use a synthetic credential
to check both normal output and reflected-secret failures; no real PAT is used
in the fixtures. GitHub's secret masking is an additional log protection.

The workflow tests first, collects data second, uploads the site artifact only
after success, and deploys only after a successful build. Failed jobs do not
deploy. It runs on `master` pushes, manually, and every six hours (UTC; GitHub
may delay scheduled runs). PRs run offline tests only, without secrets or deploys.
Updates to other repositories/Project fields become visible on the next run.
The displayed UTC timestamp identifies the last successful data collection.

Only public assets and validated JSON enter the Pages artifact; scripts,
configuration, tests, credentials and repository internals are excluded.
Generated JSON and `_site` are ignored by Git. There are no automatic commits.

If the browser cannot load or validate the JSON, it shows an unavailable message,
never a fabricated percentage or partially rendered cards. Rendering uses DOM
text nodes and validated GitHub links. JavaScript-disabled browsers get a notice;
the existing featured projects remain visible.

## Local verification

From the repository root:

```sh
python3 -m unittest discover -s tests -v
node --test tests/projects-status.test.js
```

For a live collection, securely provide `PORTFOLIO_READ_TOKEN` through your
environment, then run (do not include the token literal in the command):

```sh
python3 scripts/collect_projects_status.py
python3 -m http.server 8000
```

This writes the ignored root `projects-status.json` for local HTTP preview.
Opening `index.html` via `file://` is insufficient for a JSON fetch.

For offline preview, generate JSON from the acceptance fixtures in `tests` into
a temporary directory and serve a copy of the public site assets there. Treat
that preview as synthetic Project metadata, never as live GitHub data or a
deployable snapshot.
