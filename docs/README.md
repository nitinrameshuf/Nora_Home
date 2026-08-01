# docs/

The project's own record of itself. **These files are part of the deliverable, not
an afterthought — when code changes, they change in the same commit.** See
[`../CLAUDE.md`](../CLAUDE.md) § Documentation duty.

| File | What it is | Update when |
|---|---|---|
| [`dashboard/nora_home_dashboard.html`](dashboard/nora_home_dashboard.html) | **The main view.** Every story, its status, dependencies, and files. Click any card for detail. | A story changes status, or a new one is added |
| [`progress.md`](progress.md) | The narrative log — what happened, in order, with dates | Every working session that changes code |
| [`architecture.md`](architecture.md) | How the system fits together, with diagrams | A component, boundary, or data flow changes |
| [`capabilities.html`](capabilities.html) | What the platform can do, in plain language for the family | A capability becomes usable |
| [`design-options.html`](design-options.html) | Design directions under consideration | The design language changes |
| [`deployment-pi.md`](deployment-pi.md) | Running it on the Raspberry Pi | Deployment steps change |

## The dashboard is generated from progress.md

`dashboard/nora_home_dashboard.html` is hand-maintained today. The story data lives
in a single `STORIES` object near the bottom of the file — edit that, and the cards,
counts, and phase bars all follow. Keep `progress.md` as the prose source of truth
and the dashboard as its visual index.

## Opening them

All the HTML files are standalone — no server, no build. Open them straight from
disk, or reach the capability sheet in the running app at `/home/capabilities/`.
