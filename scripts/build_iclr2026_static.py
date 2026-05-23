"""Build a self-contained ICLR 2026 paper explorer.

Inputs are public snapshots:
- Paper Copilot processed OpenReview JSON
- PDF-derived affiliation CSV from DmytroLopushanskyy/iclr2026-affiliations
"""
from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw" / "iclr2026"
PAPERCOPILOT_JSON = RAW_DIR / "papercopilot_iclr2026.json"
AFFILIATION_CSV = RAW_DIR / "iclr2026_public_affiliations.csv"
PAPERDIGEST_CODE_HTML = RAW_DIR / "paperdigest_code_data.html"
OUT_JSON = ROOT / "output" / "iclr2026_papers.json"
OUT_HTML = ROOT / "output" / "iclr2026_explorer.html"


def split_field(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in str(value).split(";") if x.strip()]


def canonical_country(country: str) -> str:
    country = (country or "").strip()
    if country in {"Hong Kong", "Macau", "China-HK-Macau"}:
        return "China"
    return country


def canonical_countries(countries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for country in countries:
        canonical = canonical_country(country)
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


INSTITUTION_ALIASES = {
    "CUHK": "Chinese University of Hong Kong",
    "CUHK (Shenzhen)": "Chinese University of Hong Kong, Shenzhen",
    "NUS": "National University of Singapore",
    "HKUST": "Hong Kong University of Science and Technology",
    "HKUST (Guangzhou)": "Hong Kong University of Science and Technology (Guangzhou)",
    "USTC": "University of Science and Technology of China",
    "UCAS": "University of Chinese Academy of Sciences",
    "MIT": "Massachusetts Institute of Technology",
    "UIUC": "University of Illinois Urbana-Champaign",
    "NYU": "New York University",
    "UC Berkeley": "University of California, Berkeley",
    "UCLA": "University of California, Los Angeles",
    "UC San Diego": "University of California, San Diego",
    "USC": "University of Southern California",
    "UT Austin": "University of Texas at Austin",
    "Georgia Tech": "Georgia Institute of Technology",
    "NTU Singapore": "Nanyang Technological University",
    "KAIST": "Korea Advanced Institute of Science and Technology",
    "SUSTech": "Southern University of Science and Technology",
    "HUST (Wuhan)": "Huazhong University of Science and Technology",
    "MBZUAI": "Mohamed bin Zayed University of Artificial Intelligence",
    "EPFL": "횋cole Polytechnique F챕d챕rale de Lausanne",
    "UCL": "University College London",
    "BAAI": "Beijing Academy of Artificial Intelligence",
    "BIGAI": "Beijing Institute for General Artificial Intelligence",
    "CAS Institute of Automation": "Institute of Automation, Chinese Academy of Sciences",
    "CASIA": "Institute of Automation, Chinese Academy of Sciences",
    "Shanghai AI Lab": "Shanghai Artificial Intelligence Laboratory",
    "Shanghai AI Laboratory": "Shanghai Artificial Intelligence Laboratory",
    "Shanghai Innovation Institute": "Shanghai Artificial Intelligence Laboratory",
    "McGill / U Montr챕al / Mila": "Mila",
}

INSTITUTION_DROP = {
    "China",
    "USA",
    "UK",
    "Germany",
    "Singapore",
    "Australia",
    "Beijing",
    "Shanghai",
    "Shenzhen",
    "Hefei",
    "Anhui",
    "Suzhou",
    "Jiangsu",
    "Tianjin",
    "Guangzhou",
    "College Park",
    "Los Angeles",
    "Ltd",
    "MOE",
    "Department of Computer Science",
    "Department of Computer Science and Engineering",
    "Department of Computer Science and Technology",
    "Department of Electrical and Computer Engineering",
    "Department of Statistics",
    "Department of Mathematics",
    "Department of Automation",
    "Department of Artificial Intelligence",
    "School of Artificial Intelligence",
    "School of Computer Science",
    "School of Computer Science and Technology",
    "School of Computer Science and Engineering",
    "School of Intelligence Science and Technology",
    "School of Mathematical Sciences",
    "School of Data Science",
    "College of Computer Science and Artificial Intelligence",
    "College of Computer Science and Technology",
    "College of Computing and Data Science",
    "College of Science",
    "School of Engineering",
    "School of Future Technology",
    "Institute of Artificial Intelligence",
    "Institute of Artificial",
    "Institute of Artificial Intelligence for Medicine",
    "Institute of Data Science",
    "Institute of Computing Technology",
    "State Key Laboratory of General Artificial Intelligence",
    "State Key Lab of General AI",
    "State Key Lab. of AI Safety",
    "Key Laboratory of High Confidence Software Technologies",
    "Ministry of Education",
    "National Engineering Research Center For Software Engineering",
    "Center on Frontiers of Computing Studies",
    "Big Data Technology Research Center",
    "Zhiyuan College",
}


def canonical_institutions(institutions: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for inst in institutions:
        inst = re.sub(r"\s+", " ", (inst or "").strip())
        if not inst:
            continue
        inst = INSTITUTION_ALIASES.get(inst, inst)
        if inst in INSTITUTION_DROP:
            continue
        if inst and inst not in seen:
            seen.add(inst)
            out.append(inst)
    return out


def norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", title or "").strip().casefold()


def number(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list) and value:
        return number(value[0], default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bibtex_authors(bibtex: str) -> list[str]:
    if not bibtex:
        return []
    m = re.search(r"author\s*=\s*\{(.+?)\},\s*(?:year|url|journal|booktitle)", bibtex, re.S | re.I)
    if not m:
        return []
    raw = re.sub(r"\s+", " ", m.group(1)).strip()
    return [a.strip() for a in raw.split(" and ") if a.strip()]


def load_papercopilot() -> dict[str, dict]:
    rows = json.loads(PAPERCOPILOT_JSON.read_text(encoding="utf-8"))
    by_title: dict[str, dict] = {}
    for row in rows:
        key = norm_title(row.get("title", ""))
        if key and key not in by_title:
            by_title[key] = row
    return by_title


def load_paperdigest_code_links() -> tuple[dict[str, str], dict[str, str]]:
    """Return code/resource links keyed by OpenReview id and normalized title."""
    if not PAPERDIGEST_CODE_HTML.exists():
        return {}, {}
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}, {}
    soup = BeautifulSoup(PAPERDIGEST_CODE_HTML.read_text(encoding="utf-8"), "html.parser")
    by_id: dict[str, str] = {}
    by_title: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        title_link = tds[1].find("a")
        code_link = tds[3].find("a")
        view_link = None
        for a in tds[1].find_all("a"):
            href = a.get("href", "")
            if "openreview.net/forum?id=" in href:
                view_link = href
                break
        if not title_link or not code_link:
            continue
        code_url = code_link.get("href", "").strip()
        title = title_link.get_text(" ", strip=True)
        if not code_url or not title:
            continue
        by_title[norm_title(title)] = code_url
        if view_link and "=" in view_link:
            by_id[view_link.rsplit("=", 1)[-1]] = code_url
    return by_id, by_title


def build_papers() -> list[dict]:
    pc_by_title = load_papercopilot()
    code_by_id, code_by_title = load_paperdigest_code_links()
    papers: list[dict] = []
    with AFFILIATION_CSV.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            title = row.get("Title", "").strip()
            pc = pc_by_title.get(norm_title(title), {})
            url = row.get("OpenReview_URL", "").strip() or pc.get("site", "")
            forum_id = url.rsplit("=", 1)[-1] if "=" in url else pc.get("id", "")
            resource_url = (
                code_by_id.get(forum_id)
                or code_by_title.get(norm_title(title))
                or pc.get("github", "")
                or pc.get("project", "")
            )
            authors = split_field(row.get("Authors")) or split_field(pc.get("author")) or bibtex_authors(pc.get("bibtex", ""))
            institutions = canonical_institutions(
                split_field(row.get("Institutions_canonical"))
                or split_field(row.get("Institutions"))
                or split_field(pc.get("aff_unique_norm"))
            )
            countries = canonical_countries(split_field(row.get("Countries")) or split_field(pc.get("aff_country_unique")))
            keywords = split_field(row.get("Keywords")) or split_field(pc.get("keywords"))
            paper = {
                "id": forum_id or f"iclr2026-{idx}",
                "code": forum_id or f"{idx:04d}",
                "status": row.get("Decision", "").strip() or pc.get("status", ""),
                "title": title,
                "authors": authors,
                "institutions": institutions,
                "countries": countries,
                "regions": split_field(row.get("Regions")),
                "affiliation_source": row.get("Affiliation_source", "").strip(),
                "primary_area": row.get("Primary_Area", "").strip() or pc.get("primary_area", ""),
                "keywords": keywords,
                "abstract": row.get("Abstract", "").strip() or pc.get("abstract", ""),
                "tldr": pc.get("tldr", ""),
                "openreview_url": url,
                "pdf_url": f"https://openreview.net/pdf?id={forum_id}" if forum_id else "",
                "resource_url": resource_url,
                "resource_source": "Paper Digest" if resource_url else "",
                "rating_avg": number(pc.get("rating_avg")),
                "confidence_avg": number(pc.get("confidence_avg")),
                "ratings": split_field(pc.get("rating")),
                "citations": number(pc.get("gs_citation"), 0),
            }
            papers.append(paper)
    return papers


def dataset_summary(papers: list[dict]) -> dict:
    def top(counter: Counter, n: int) -> list[dict]:
        return [{"name": k, "count": v} for k, v in counter.most_common(n) if k]

    return {
        "conference": "ICLR 2026",
        "generated": "2026-05-23",
        "n_papers": len(papers),
        "sources": [
            {
                "name": "Paper Copilot ICLR 2026 JSON",
                "url": "https://github.com/papercopilot/paperlists/blob/main/iclr/iclr2026.json",
                "note": "Processed OpenReview metadata, ratings, links, and review-derived fields.",
            },
            {
                "name": "ICLR 2026 PDF-derived affiliation dataset",
                "url": "https://github.com/DmytroLopushanskyy/iclr2026-affiliations",
                "note": "Accepted-paper authors, affiliations, countries, regions, areas, keywords, abstracts.",
            },
            {
                "name": "ICLR 2026 OpenReview group",
                "url": "https://openreview.net/group?id=ICLR.cc/2026/Conference",
                "note": "Canonical paper/forum links and public review venue.",
            },
        ],
        "status_counts": top(Counter(p["status"] for p in papers), 10),
        "area_counts": top(Counter(p["primary_area"] for p in papers), 30),
        "country_counts": top(Counter(c for p in papers for c in set(p["countries"]) if c and c != "Other"), 30),
        "institution_counts": top(Counter(i for p in papers for i in set(p["institutions"]) if i), 30),
        "keyword_counts": top(Counter(k for p in papers for k in set(p["keywords"]) if k), 50),
        "code_count": sum(1 for p in papers if p["resource_url"]),
    }


def write_outputs() -> None:
    papers = build_papers()
    summary = dataset_summary(papers)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"summary": summary, "papers": papers}, ensure_ascii=False, indent=2), encoding="utf-8")
    data_json = json.dumps({"summary": summary, "papers": papers}, ensure_ascii=False, separators=(",", ":"))
    OUT_HTML.write_text(render_html(data_json), encoding="utf-8")


def render_html(data_json: str) -> str:
    escaped = html.escape(data_json, quote=False)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICLR 2026 · Paper Explorer</title>
<style>
:root {{
  --bg:#ffffff; --soft:#f5f5f7; --line:#d8d8de; --text:#1d1d1f; --muted:#6e6e73;
  --accent:#0066cc; --green:#1f7a4d; --orange:#b45b00; --purple:#6d45c7; --shadow:0 1px 3px rgba(0,0,0,.08);
  --font:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Pretendard,"Noto Sans KR",system-ui,sans-serif;
}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:var(--font);font-size:15px;line-height:1.5}}
a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
.top{{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.88);backdrop-filter:blur(18px);border-bottom:1px solid #e5e5ea}}
.topin{{max-width:1440px;margin:auto;padding:12px 24px;display:flex;align-items:center;gap:14px}} .brand{{font-weight:700;font-size:17px;cursor:pointer}}
.pill{{border:1px solid #e5e5ea;background:var(--soft);border-radius:999px;padding:4px 10px;color:var(--muted);font-size:12px}} .top .right{{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}}
.wrap{{max-width:1440px;margin:auto;padding:26px 24px 60px}} .hero{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:28px;align-items:end;margin-bottom:26px}}
h1{{font-size:46px;line-height:1.04;margin:0 0 12px;letter-spacing:0}} .lede{{font-size:18px;color:#424245;max-width:880px;margin:0}}
.source{{font-size:12px;color:var(--muted);margin-top:14px}} .stats{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}
.stat{{border:1px solid #e5e5ea;border-radius:8px;padding:14px;background:#fff;box-shadow:var(--shadow)}} .num{{font-size:28px;font-weight:700}} .lab{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
.grid{{display:grid;grid-template-columns:300px minmax(0,1fr);gap:28px}} aside{{position:sticky;top:60px;align-self:start;max-height:calc(100vh - 70px);overflow:auto;padding-bottom:20px}}
.panel{{border:1px solid #e5e5ea;border-radius:8px;background:#fff;box-shadow:var(--shadow);padding:14px;margin-bottom:14px}} h2{{font-size:22px;margin:0 0 10px}} h3{{font-size:13px;margin:0 0 10px;color:#424245}}
.panel-head{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}} .panel-head h3{{margin:0}} .mini-toggle{{border:1px solid #d2d2d7;background:#fff;border-radius:999px;padding:3px 8px;font-size:11px;color:var(--muted);line-height:1.2}} .mini-toggle:hover{{border-color:var(--accent);color:var(--accent)}}
label{{display:block;font-size:12px;color:var(--muted);margin:11px 0 5px}} input,select{{width:100%;border:1px solid #c7c7cc;border-radius:7px;padding:9px 10px;font:inherit;background:#fff}} input.active-filter,select.active-filter{{background:#eef6ff;border-color:#8ec5ff;color:#064b8e}} button{{border:1px solid #c7c7cc;background:#fff;border-radius:7px;padding:8px 10px;font:inherit;cursor:pointer}} button:hover{{border-color:var(--accent);color:var(--accent)}} button.reset{{background:#fff1f2;border-color:#fecdd3;color:#9f1239}} button.reset:hover{{background:#ffe4e6;border-color:#fb7185;color:#881337}}
.bar{{display:grid;grid-template-columns:minmax(110px,1fr) 52px;gap:10px;align-items:center;margin:7px 0;font-size:13px;cursor:pointer;border:1px solid transparent;border-radius:7px;padding:3px 5px}} .bar:hover .name{{color:var(--accent)}} .bar.active-filter{{background:#eef6ff;border-color:#8ec5ff}} .bar.active-filter .name,.bar.active-filter .count{{color:#064b8e;font-weight:600}} .track{{height:8px;background:#ececf1;border-radius:99px;overflow:hidden;grid-column:1/3}} .fill{{height:100%;background:var(--accent)}} .count{{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}} .chip{{border:1px solid #e5e5ea;background:var(--soft);border-radius:999px;padding:4px 9px;font-size:12px;color:#424245;cursor:pointer}} .chip:hover{{border-color:var(--accent);color:var(--accent)}} .chip.active-filter{{background:#eef6ff;border-color:#8ec5ff;color:#064b8e;font-weight:600}}
.tools{{display:grid;grid-template-columns:1.4fr repeat(4,minmax(130px,.5fr));gap:10px;margin-bottom:12px}} .resultsMeta{{font-size:13px;color:var(--muted);margin:8px 0 12px}}
.papers{{display:grid;gap:10px}} .paper{{border:1px solid #e5e5ea;border-radius:8px;padding:14px 16px;background:#fff;box-shadow:var(--shadow)}} .paper.open{{border-color:#a8c7fa}}
.ptop{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:7px}} .badge{{font-size:11px;border-radius:999px;padding:3px 8px;background:var(--soft);color:#424245}} .badge.oral{{background:#fff4e5;color:var(--orange)}} .badge.poster{{background:#eef7f1;color:var(--green)}}
.title{{font-size:17px;font-weight:700;line-height:1.32;cursor:pointer}} .authors{{font-size:13px;color:#424245;margin-top:6px}} .author-link{{border-radius:5px;padding:1px 3px;cursor:pointer}} .author-link:hover{{background:var(--accent-soft);color:var(--accent)}} .author-link.active-filter{{background:#eef6ff;color:#064b8e;font-weight:600}} .meta{{font-size:12px;color:var(--muted);margin-top:7px}} .abstract{{display:none;border-left:3px solid var(--accent);background:#fafafa;margin-top:12px;padding:11px 13px;border-radius:0 7px 7px 0;color:#303033}} .paper.open .abstract{{display:block}}
.paper-keywords{{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}} .paper-keyword{{border:1px solid #e5e5ea;background:#fafafa;border-radius:999px;padding:2px 8px;font-size:11px;color:#424245;cursor:pointer}} .paper-keyword:hover{{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}} .paper-keyword.active-filter{{background:#eef6ff;border-color:#8ec5ff;color:#064b8e;font-weight:600}}
.links{{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;font-size:13px}} .empty{{color:var(--muted);font-style:italic}} .pager{{display:flex;gap:8px;justify-content:center;margin-top:18px}}
@media(max-width:1050px){{.hero,.grid{{grid-template-columns:1fr}} aside{{position:static;max-height:none}} .tools{{grid-template-columns:1fr 1fr}} h1{{font-size:36px}}}}
@media(max-width:620px){{.wrap,.topin{{padding-left:14px;padding-right:14px}} .stats,.tools{{grid-template-columns:1fr}} .top .right .pill:not(:first-child){{display:none}}}}
</style>
</head>
<body>
<script id="dataset" type="application/json">{escaped}</script>
<div class="top"><div class="topin"><div class="brand" onclick="resetAll()">ICLR 2026 · Paper Explorer</div><span class="pill">static HTML</span><div class="right"><span class="pill" id="topCount"></span><span class="pill" id="topCode"></span></div></div></div>
<div class="wrap">
  <section class="hero">
    <div>
      <h1>ICLR 2026 Paper Explorer</h1>
      <p class="lede">Accepted ICLR 2026 papers, searchable by title, author, institution, country, primary area, keyword, abstract, OpenReview score, and public code/data/project links.</p>
      <div class="source">Sources: OpenReview-derived Paper Copilot metadata + PDF-derived affiliation dataset. Counts can differ slightly from the official ICLR blog because public snapshots update after decisions and withdrawals.</div>
    </div>
    <div class="stats" id="stats"></div>
  </section>
  <div class="grid">
    <aside>
      <div class="panel"><h3>Decision</h3><div id="statusBars"></div></div>
      <div class="panel"><h3>Top Primary Areas</h3><div id="areaBars"></div></div>
      <div class="panel"><div class="panel-head"><h3>Top Countries</h3><button class="mini-toggle" id="countryToggle">Show 30</button></div><div id="countryBars"></div></div>
      <div class="panel"><div class="panel-head"><h3>Top Institutions</h3><button class="mini-toggle" id="instToggle">Show 70</button></div><div id="instBars"></div></div>
      <div class="panel"><h3>Frequent Keywords</h3><div id="keywordChips" class="chips"></div></div>
    </aside>
    <main>
      <section class="panel">
        <h2>Find papers</h2>
        <div class="tools">
          <input id="q" placeholder="Search title, authors, institutions, countries, keywords, abstract">
          <select id="status"><option value="">All decisions</option></select>
          <select id="area"><option value="">All primary areas</option></select>
          <select id="country"><option value="">All countries</option></select>
          <select id="sort"><option value="rating">Rating</option><option value="title">Title</option><option value="citations">Citations</option><option value="authors">Authors</option></select>
        </div>
        <div class="tools" style="grid-template-columns:repeat(5,minmax(120px,1fr));">
          <select id="codeFilter"><option value="">Resource link: any</option><option value="yes">Has code/data/project</option><option value="no">No public resource link</option></select>
          <select id="source"><option value="">Affiliation source: any</option></select>
          <select id="pageSize"><option value="30">30 per page</option><option value="60">60 per page</option><option value="100">100 per page</option><option value="200">200 per page</option><option value="500" selected>500 per page</option><option value="1000">1000 per page</option><option value="2000">2000 per page</option><option value="5000">5000 per page</option><option value="10000">10000 per page</option></select>
          <button class="reset" onclick="resetAll()">Reset filters</button>
          <button onclick="downloadJson()">Download filtered JSON</button>
        </div>
        <div id="resultsMeta" class="resultsMeta"></div>
        <div id="papers" class="papers"></div>
        <div class="pager"><button id="prev">Previous</button><button id="next">Next</button></div>
      </section>
    </main>
  </div>
</div>
<script>
const DATA = JSON.parse(document.getElementById('dataset').textContent);
const PAPERS = DATA.papers;
const S = DATA.summary;
let page = 0, pageSize = 500;
let expandedCountries = false, expandedInstitutions = false;
const $ = id => document.getElementById(id);
const uniq = arr => [...new Set(arr.filter(Boolean))].sort((a,b)=>a.localeCompare(b));
function fmt(n){{ return Number(n || 0).toLocaleString(); }}
function attr(s){{ return String(s ?? '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function text(s){{ return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function addOptions(id, values){{ const el=$(id); values.forEach(v=>{{ const o=document.createElement('option'); o.value=v; o.textContent=v; el.appendChild(o); }}); }}
function renderStats(){{
  $('topCount').textContent = fmt(S.n_papers) + ' accepted papers';
  $('topCode').textContent = fmt(S.code_count) + ' with code/project';
  $('stats').innerHTML = [
    ['Accepted papers', S.n_papers], ['Orals', (S.status_counts.find(x=>x.name==='Oral')||{{count:0}}).count],
    ['Primary areas', uniq(PAPERS.map(p=>p.primary_area)).length], ['Code/project links', S.code_count]
  ].map(x=>`<div class="stat"><div class="lab">${{x[0]}}</div><div class="num">${{fmt(x[1])}}</div></div>`).join('');
}}
function bars(id, rows, field, maxRows=12){{
  const max = Math.max(...rows.slice(0,maxRows).map(r=>r.count), 1);
  $(id).innerHTML = rows.slice(0,maxRows).map(r=>`<div class="bar" data-filter-field="${{attr(field)}}" data-filter-value="${{attr(r.name)}}"><span class="name">${{r.name}}</span><span class="count">${{fmt(r.count)}}</span><span class="track"><span class="fill" style="width:${{100*r.count/max}}%"></span></span></div>`).join('');
}}
function renderExpandableBars(){{
  bars('countryBars', S.country_counts, 'country', expandedCountries ? 30 : 12);
  bars('instBars', S.institution_counts, 'q', expandedInstitutions ? 70 : 12);
  $('countryToggle').textContent = expandedCountries ? 'Show 12' : 'Show 30';
  $('instToggle').textContent = expandedInstitutions ? 'Show 12' : 'Show 70';
  updateActiveFilters();
}}
function setFilter(field, value){{
  if(field === 'status') $('status').value = $('status').value === value ? '' : value;
  if(field === 'area') $('area').value = $('area').value === value ? '' : value;
  if(field === 'country') $('country').value = $('country').value === value ? '' : value;
  if(field === 'q') $('q').value = $('q').value === value ? '' : value;
  page=0; render();
}}
function setQuery(value){{ $('q').value = $('q').value === value ? '' : value; page=0; render(); }}
globalThis.setFilter = setFilter;
globalThis.setQuery = setQuery;
function resetAll(){{ ['q','status','area','country','sort','codeFilter','source'].forEach(id=>$(id).value=''); $('sort').value='rating'; page=0; render(); window.scrollTo({{top:0, behavior:'smooth'}}); }}
function chips(){{
  $('keywordChips').innerHTML = S.keyword_counts.slice(0,80).map(k=>`<span class="chip" data-query="${{attr(k.name)}}">${{k.name}} · ${{fmt(k.count)}}</span>`).join('');
}}
function updateActiveFilters(){{
  const active = {{
    q: $('q').value.trim(),
    status: $('status').value,
    area: $('area').value,
    country: $('country').value
  }};
  document.querySelectorAll('.bar[data-filter-field]').forEach(el => {{
    const field = el.dataset.filterField;
    el.classList.toggle('active-filter', Boolean(active[field]) && el.dataset.filterValue === active[field]);
  }});
  document.querySelectorAll('.chip[data-query]').forEach(el => {{
    el.classList.toggle('active-filter', Boolean(active.q) && el.dataset.query.toLowerCase() === active.q.toLowerCase());
  }});
  document.querySelectorAll('.paper-keyword[data-query]').forEach(el => {{
    el.classList.toggle('active-filter', Boolean(active.q) && el.dataset.query.toLowerCase() === active.q.toLowerCase());
  }});
  document.querySelectorAll('.author-link[data-author]').forEach(el => {{
    el.classList.toggle('active-filter', Boolean(active.q) && el.dataset.author.toLowerCase() === active.q.toLowerCase());
  }});
  ['q','status','area','country','codeFilter','source'].forEach(id => {{
    const el = $(id);
    el.classList.toggle('active-filter', Boolean(el.value && String(el.value).trim()));
  }});
}}
function hay(p){{ return [p.title,p.authors.join(' '),p.institutions.join(' '),p.countries.join(' '),p.primary_area,p.keywords.join(' '),p.abstract,p.tldr].join(' ').toLowerCase(); }}
function filtered(){{
  const q=$('q').value.trim().toLowerCase(), st=$('status').value, area=$('area').value, c=$('country').value, code=$('codeFilter').value, src=$('source').value;
  let rows=PAPERS.filter(p=>(!q||hay(p).includes(q))&&(!st||p.status===st)&&(!area||p.primary_area===area)&&(!c||p.countries.includes(c))&&(!src||p.affiliation_source===src)&&(!code||(code==='yes'?p.resource_url:!p.resource_url)));
  const sort=$('sort').value;
  rows.sort((a,b)=> sort==='title' ? a.title.localeCompare(b.title) : sort==='citations' ? (b.citations||0)-(a.citations||0) : sort==='authors' ? b.authors.length-a.authors.length : (b.rating_avg||0)-(a.rating_avg||0));
  return rows;
}}
function paperHtml(p){{
  const badge = (p.status||'').toLowerCase().includes('oral') ? 'oral' : 'poster';
  const rating = p.rating_avg ? ` · rating ${{p.rating_avg.toFixed(2)}}` : '';
  const country = p.countries.slice(0,6).join(', ');
  const inst = p.institutions.slice(0,8).join('; ');
  const links = [`<a href="${{p.openreview_url}}" target="_blank">OpenReview</a>`, p.pdf_url ? `<a href="${{p.pdf_url}}" target="_blank">PDF</a>` : '', p.resource_url ? `<a href="${{p.resource_url}}" target="_blank">Code/Data/Project</a>` : ''].filter(Boolean).join('');
  const authors = p.authors.slice(0,20).map(a => `<span class="author-link" data-author="${{attr(a)}}">${{text(a)}}</span>`).join('; ');
  const visibleKeywords = p.keywords.slice(0,6).map(k => `<span class="paper-keyword" data-query="${{attr(k)}}">${{text(k)}}</span>`).join('');
  const moreKeywords = p.keywords.length > 6 ? `<span class="badge">+${{p.keywords.length - 6}} keywords</span>` : '';
  return `<article class="paper"><div class="ptop"><span class="badge ${{badge}}">${{p.status}}</span><span class="badge">${{p.primary_area || 'No area'}}</span>${{p.resource_url?'<span class="badge">resource</span>':''}}</div><div class="title" onclick="this.closest('.paper').classList.toggle('open')">${{p.title}}</div><div class="authors">${{authors || '<span class="empty">authors unavailable</span>'}}</div><div class="paper-keywords">${{visibleKeywords || '<span class="empty">no keywords</span>'}}${{moreKeywords}}</div><div class="meta">${{country || 'country unavailable'}}${{rating}} · ${{p.authors.length}} authors</div><div class="abstract"><div><b>Institutions:</b> ${{inst || '<span class="empty">unavailable</span>'}}</div><div style="margin-top:8px"><b>Keywords:</b> ${{p.keywords.join('; ') || '<span class="empty">none</span>'}}</div><div style="margin-top:10px">${{p.abstract || '<span class="empty">abstract unavailable</span>'}}</div><div class="links">${{links}}</div></div></article>`;
}}
function render(){{
  pageSize = Number($('pageSize')?.value || pageSize);
  const rows=filtered(), maxPage=Math.max(0, Math.ceil(rows.length/pageSize)-1); page=Math.min(page,maxPage);
  const start=page*pageSize, shown=rows.slice(start,start+pageSize);
  $('resultsMeta').textContent = `${{fmt(rows.length)}} results · page ${{page+1}} / ${{maxPage+1}}`;
  $('papers').innerHTML = shown.map(paperHtml).join('');
  $('prev').disabled = page===0; $('next').disabled = page>=maxPage;
  updateActiveFilters();
}}
function downloadJson(){{
  const blob = new Blob([JSON.stringify({{summary:S, papers:filtered()}}, null, 2)], {{type:'application/json'}});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'iclr2026_filtered_papers.json'; a.click(); URL.revokeObjectURL(a.href);
}}
function init(){{
  renderStats(); bars('statusBars', S.status_counts, 'status', 8); bars('areaBars', S.area_counts, 'area', 12); renderExpandableBars(); chips();
  addOptions('status', uniq(PAPERS.map(p=>p.status))); addOptions('area', uniq(PAPERS.map(p=>p.primary_area))); addOptions('country', uniq(PAPERS.flatMap(p=>p.countries).filter(c=>c!=='Other'))); addOptions('source', uniq(PAPERS.map(p=>p.affiliation_source)));
  document.addEventListener('click', e => {{
    const author = e.target.closest('.author-link[data-author]');
    if (author) {{
      e.stopPropagation();
      setQuery(author.dataset.author);
      return;
    }}
    const paperKeyword = e.target.closest('.paper-keyword[data-query]');
    if (paperKeyword) {{
      e.stopPropagation();
      setQuery(paperKeyword.dataset.query);
      return;
    }}
    const keywordChip = e.target.closest('.chip[data-query]');
    if (keywordChip) {{
      e.stopPropagation();
      setQuery(keywordChip.dataset.query);
      return;
    }}
    if (e.target.id === 'countryToggle') {{
      expandedCountries=!expandedCountries;
      renderExpandableBars();
      return;
    }}
    if (e.target.id === 'instToggle') {{
      expandedInstitutions=!expandedInstitutions;
      renderExpandableBars();
      return;
    }}
    const bar = e.target.closest('.bar[data-filter-field]');
    if (bar) setFilter(bar.dataset.filterField, bar.dataset.filterValue);
  }});
  ['q','status','area','country','sort','codeFilter','source','pageSize'].forEach(id=>$(id).addEventListener('input',()=>{{page=0;render();}}));
  $('prev').onclick=()=>{{page--;render();}}; $('next').onclick=()=>{{page++;render();}};
  render();
}}
init();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    write_outputs()



