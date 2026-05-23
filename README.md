# ICLR 2026 Paper Explorer

Local static explorer for ICLR 2026 accepted papers.

Live demo:

- https://gisbi-kim.github.io/iclr2026-explorer/

Open this file in a browser:

- `output/iclr2026_explorer.html`

## Snapshot

| Item | Value |
|---|---:|
| Papers in this snapshot | 5,356 |
| Oral | 225 |
| Poster | 5,131 |
| Papers with code/data/project links | 1,180 |
| Primary areas | 21 |

## Features

- Search title, author, institution, country, primary area, keyword, and abstract
- Filter by decision, primary area, country, affiliation source, and resource-link availability
- Sort by rating, citation count, title, or author count
- Share filtered states through the URL query string
- Expand paper cards for abstract, institutions, keywords, OpenReview, PDF, and resource links
- Download the filtered result set as JSON

## Data Sources

- Paper metadata, ratings, links: https://github.com/papercopilot/paperlists/blob/main/iclr/iclr2026.json
- Accepted-paper affiliations and countries: https://github.com/DmytroLopushanskyy/iclr2026-affiliations
- Code/data/project links: https://resources.paperdigest.org/2026/04/iclr-2026-papers-with-code-data/
- Canonical venue page: https://openreview.net/group?id=ICLR.cc/2026/Conference
- Official process/count context: https://blog.iclr.cc/2026/03/31/a-retrospective-on-the-iclr-2026-review-process/

The official ICLR retrospective reports 5,355 accepted papers. This static explorer uses the public affiliation snapshot, which contains 5,356 accepted-paper rows. Treat the one-paper difference as a snapshot/update artifact.

## Rebuild

```bash
python scripts/build_iclr2026_static.py
```

The generated HTML embeds the normalized JSON, so it can be hosted on GitHub Pages later or opened directly from disk.
