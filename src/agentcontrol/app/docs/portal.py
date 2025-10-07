"""Static documentation portal generator."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from agentcontrol.app.architecture.generator import generate_doc_sections, load_manifest_from_path
from agentcontrol.app.docs.operations import DocsCommandService
from agentcontrol.app.docs.utils import (
    extract_summary,
    extract_title,
    iso_mtime,
    safe_relpath,
    truncate_summary,
    utc_now_iso,
)
from agentcontrol.domain.docs.constants import remediation_for
from agentcontrol.domain.docs.value_objects import DocsBridgeConfigError
from agentcontrol.utils.docs_bridge import load_docs_bridge_config

PORTAL_DEFAULT_BUDGET = 1_048_576  # 1 MiB
PORTAL_DEFAULT_SUBDIR = Path("reports/docs/portal")
ASSETS_SUBDIR = Path("assets")


@dataclass(frozen=True)
class DocsPortalResult:
    """Outcome metadata for generated portal."""

    output_path: Path
    file_count: int
    total_size_bytes: int
    generated_at: str
    inventory_counts: Dict[str, int]


class DocsPortalError(RuntimeError):
    """Raised when docs portal generation fails."""

    def __init__(self, code: str, message: str, remediation: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.remediation = remediation if remediation is not None else remediation_for(code)


class DocsPortalGenerator:
    """Render a self-contained HTML portal for documentation assets."""

    def __init__(self, command_service: Optional[DocsCommandService] = None, *, size_budget: int = PORTAL_DEFAULT_BUDGET) -> None:
        self._command_service = command_service or DocsCommandService()
        self._size_budget = size_budget

    def generate(
        self,
        project_root: Path,
        *,
        output_dir: Optional[Path] = None,
        budget: Optional[int] = None,
        force: bool = False,
    ) -> DocsPortalResult:
        project_root = project_root.resolve()
        output_path = (output_dir or (project_root / PORTAL_DEFAULT_SUBDIR)).resolve()
        size_budget = budget if budget is not None else self._size_budget

        manifest_path = self._discover_manifest(project_root)
        manifest = load_manifest_from_path(manifest_path)
        doc_sections = generate_doc_sections(manifest)

        try:
            config, _ = load_docs_bridge_config(project_root)
        except DocsBridgeConfigError as exc:
            raise DocsPortalError(exc.code, exc.message, exc.remediation) from exc

        docs_root = config.absolute_root(project_root)
        docs_status = self._command_service.list_sections(project_root)

        generated_at = utc_now_iso()
        sections_payload = self._build_sections_payload(doc_sections, manifest_path, project_root)
        inventory = self._build_inventory(project_root, docs_root)
        inventory_counts = dict(Counter(entry["kind"] for entry in inventory))
        docs_root_display = safe_relpath(docs_root, project_root)
        status_snapshot = {
            "configPath": docs_status.get("configPath"),
            "rootExists": docs_status.get("rootExists"),
            "sections": docs_status.get("sections", []),
        }

        portal_payload = {
            "generated_at": generated_at,
            "project_root": str(project_root),
            "docs_root": docs_root_display,
            "sections": sections_payload,
            "status": status_snapshot,
            "inventory": inventory,
        }

        self._prepare_output(output_path, force=force)
        assets_dir = output_path / ASSETS_SUBDIR
        assets_dir.mkdir(parents=True, exist_ok=True)

        _write_text(output_path / "index.html", self._render_index_html(portal_payload))
        _write_text(assets_dir / "styles.css", _STYLESHEET)
        _write_text(assets_dir / "snarkdown.js", _SNARKDOWN_JS)
        _write_text(assets_dir / "app.js", _APP_JS)

        total_size = _directory_size(output_path)
        if total_size > size_budget:
            shutil.rmtree(output_path, ignore_errors=True)
            raise DocsPortalError(
                "DOCS_PORTAL_SIZE_BUDGET_EXCEEDED",
                f"Generated portal size {total_size} bytes exceeds budget {size_budget}",
            )

        file_count = sum(1 for path in output_path.rglob("*") if path.is_file())
        return DocsPortalResult(
            output_path=output_path,
            file_count=file_count,
            total_size_bytes=total_size,
            generated_at=generated_at,
            inventory_counts=inventory_counts,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_sections_payload(self, sections, manifest_path: Path, project_root: Path) -> List[Dict[str, str]]:
        manifest_source = safe_relpath(manifest_path, project_root)
        return [
            {
                "id": "architecture_overview",
                "title": "Architecture Overview",
                "markdown": sections.architecture_overview.strip(),
                "source": manifest_source,
            },
            {
                "id": "adr_index",
                "title": "ADR Index",
                "markdown": sections.adr_index.strip(),
                "source": manifest_source,
            },
            {
                "id": "rfc_index",
                "title": "RFC Index",
                "markdown": sections.rfc_index.strip(),
                "source": manifest_source,
            },
        ]

    def _build_inventory(self, project_root: Path, docs_root: Path) -> List[Dict[str, object]]:
        entries: List[Dict[str, object]] = []
        tutorials_root = docs_root / "tutorials"
        entries.extend(self._collect_markdown_entries(project_root, tutorials_root, kind="tutorial", default_tags=["docs", "tutorial"]))

        examples_root = project_root / "examples"
        entries.extend(self._collect_example_entries(project_root, examples_root))

        return sorted(entries, key=lambda item: (item["kind"], item["title"]))

    def _collect_markdown_entries(
        self,
        project_root: Path,
        base: Path,
        *,
        kind: str,
        default_tags: Iterable[str],
    ) -> List[Dict[str, object]]:
        if not base.exists():
            return []
        results: List[Dict[str, object]] = []
        for path in sorted(base.rglob("*.md")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            title = extract_title(text, fallback=path.stem)
            summary = extract_summary(text)
            tags = list(default_tags) + [segment.replace("_", "-") for segment in path.relative_to(base).parts[:-1]]
            results.append(
                {
                    "kind": kind,
                    "title": title,
                    "path": safe_relpath(path, project_root),
                    "summary": summary,
                    "tags": sorted(set(tags)),
                    "modified_at": iso_mtime(path),
                }
            )
        return results

    def _collect_example_entries(self, project_root: Path, base: Path) -> List[Dict[str, object]]:
        if not base.exists():
            return []
        entries: List[Dict[str, object]] = []
        for directory in sorted(base.iterdir()):
            if not directory.is_dir():
                continue
            readme = directory / "README.md"
            if readme.exists():
                text = readme.read_text(encoding="utf-8")
                title = extract_title(text, fallback=directory.name)
                summary = extract_summary(text)
                entry_path = readme
            else:
                title = directory.name.replace("_", " ").title()
                summary = "Пример без README.md: изучите содержимое каталога."
                entry_path = directory
            tags = ["examples"] + [segment.replace("_", "-") for segment in directory.relative_to(base).parts]
            entries.append(
                {
                    "kind": "example",
                    "title": title,
                    "path": safe_relpath(entry_path, project_root),
                    "summary": truncate_summary(summary),
                    "tags": sorted(set(tags)),
                    "modified_at": iso_mtime(entry_path),
                }
            )
        return entries

    def _prepare_output(self, output_path: Path, *, force: bool) -> None:
        if output_path.exists():
            if _looks_like_portal(output_path):
                shutil.rmtree(output_path, ignore_errors=True)
            elif not force and any(output_path.iterdir()):
                raise DocsPortalError(
                    "DOCS_PORTAL_OUTPUT_NOT_EMPTY",
                    f"Output directory {output_path} is not empty. Use --force to overwrite.",
                )
            else:
                shutil.rmtree(output_path, ignore_errors=True)
        output_path.mkdir(parents=True, exist_ok=True)

    def _render_index_html(self, payload: Dict[str, object]) -> str:
        data = json.dumps(payload, ensure_ascii=False)
        data = data.replace("</", "<\\/")  # avoid closing script tag injection
        return (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "  <title>AgentControl Docs Portal</title>\n"
            '  <link rel="stylesheet" href="assets/styles.css">\n'
            "</head>\n"
            "<body>\n"
            "  <header class=\"portal-header\">\n"
            "    <div>\n"
            "      <h1>AgentControl Docs Portal</h1>\n"
            "      <p id=\"portal-meta\"></p>\n"
            "    </div>\n"
            "    <div class=\"search\">\n"
            '      <label for="portal-search">Search</label>\n'
            '      <input id="portal-search" type="search" placeholder="Tutorials, examples, tags...">\n'
            "    </div>\n"
            "  </header>\n"
            "  <main>\n"
            "    <section class=\"status\">\n"
            "      <h2>Docs Status</h2>\n"
            "      <ul id=\"status-list\"></ul>\n"
            "    </section>\n"
            "    <section class=\"search-results\">\n"
            "      <h2>Knowledge Inventory</h2>\n"
            "      <ul id=\"search-results\"></ul>\n"
            "    </section>\n"
            "    <section class=\"managed-sections\">\n"
            "      <h2>Managed Sections</h2>\n"
            "      <div id=\"managed-sections\"></div>\n"
            "    </section>\n"
            "  </main>\n"
            f"  <script>const portalData = {data}; window.__AGENTCONTROL_DOCS_PORTAL__ = portalData;</script>\n"
            '  <script src="assets/snarkdown.js"></script>\n'
            '  <script src="assets/app.js"></script>\n'
            "</body>\n"
            "</html>\n"
        )

    def _discover_manifest(self, project_root: Path) -> Path:
        candidates = [
            project_root / "architecture" / "manifest.yaml",
            project_root / ".agentcontrol" / "architecture" / "manifest.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        raise DocsPortalError(
            "DOCS_PORTAL_MANIFEST_MISSING",
            "architecture/manifest.yaml (or .agentcontrol/architecture/manifest.yaml) not found",
        )
def _looks_like_portal(output_path: Path) -> bool:
    return (
        (output_path / "index.html").exists()
        and (output_path / ASSETS_SUBDIR).is_dir()
        and (output_path / ASSETS_SUBDIR / "app.js").exists()
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _directory_size(root: Path) -> int:
    return sum(file.stat().st_size for file in root.rglob("*") if file.is_file())


_STYLESHEET = """
:root {
  color-scheme: light dark;
  --bg: #0f1115;
  --fg: #f5f7fa;
  --surface: #1b1f27;
  --accent: #5aa9ff;
  --muted: #8892a6;
  font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
}

@media (prefers-color-scheme: light) {
  :root {
    --bg: #f7f9fc;
    --fg: #111521;
    --surface: #ffffff;
    --muted: #4b5567;
  }
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  min-height: 100vh;
}

.portal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding: 2.5rem 3rem 1.5rem;
  background: var(--surface);
  gap: 2rem;
}

.portal-header h1 {
  margin: 0 0 0.5rem;
  font-size: 2.2rem;
}

.portal-header p {
  margin: 0;
  color: var(--muted);
  font-size: 0.95rem;
}

.portal-header .search {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  width: min(340px, 100%);
}

.portal-header input {
  background: var(--bg);
  border: 1px solid rgba(138, 150, 171, 0.35);
  border-radius: 0.75rem;
  padding: 0.7rem 1rem;
  color: var(--fg);
  font-size: 1rem;
}

main {
  display: grid;
  grid-template-columns: minmax(260px, 320px) 1fr;
  gap: 2rem;
  padding: 2rem 3rem 3rem;
}

section {
  background: var(--surface);
  border-radius: 1rem;
  padding: 1.5rem;
  box-shadow: 0 14px 35px rgba(0, 0, 0, 0.16);
}

section h2 {
  margin-top: 0;
  font-size: 1.4rem;
}

#status-list,
#search-results {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  border-left: 4px solid var(--accent);
  padding-left: 0.75rem;
}

.status-item span {
  font-size: 0.9rem;
  color: var(--muted);
}

.search-hit {
  padding: 1rem 1.2rem;
  border-radius: 0.75rem;
  background: rgba(90, 169, 255, 0.08);
  border: 1px solid rgba(90, 169, 255, 0.25);
}

.search-hit h3 {
  margin: 0 0 0.35rem;
  font-size: 1.1rem;
}

.search-hit p {
  margin: 0 0 0.6rem;
  font-size: 0.92rem;
  color: var(--muted);
}

.search-hit .meta {
  font-size: 0.8rem;
  color: var(--muted);
}

#managed-sections article {
  margin-bottom: 2.5rem;
  padding-bottom: 2.5rem;
  border-bottom: 1px solid rgba(138, 150, 171, 0.2);
}

#managed-sections article:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

#managed-sections h3 {
  margin: 0 0 0.75rem;
  font-size: 1.3rem;
}

#managed-sections .section-meta {
  font-size: 0.85rem;
  color: var(--muted);
  margin-bottom: 1.1rem;
}

#managed-sections .section-content {
  line-height: 1.65;
  display: grid;
  gap: 1.1rem;
}

#managed-sections table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

#managed-sections th,
#managed-sections td {
  border: 1px solid rgba(138, 150, 171, 0.4);
  padding: 0.5rem 0.7rem;
  text-align: left;
}

#managed-sections th {
  background: rgba(90, 169, 255, 0.15);
}

code {
  font-family: "JetBrains Mono", "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  background: rgba(138, 150, 171, 0.25);
  padding: 0.05rem 0.35rem;
  border-radius: 0.4rem;
  font-size: 0.85rem;
}

@media (max-width: 960px) {
  main {
    grid-template-columns: 1fr;
  }
}
""".strip()

_APP_JS = """
(function () {
  const data = window.__AGENTCONTROL_DOCS_PORTAL__;
  if (!data) {
    return;
  }

  const metaEl = document.getElementById("portal-meta");
  const statusList = document.getElementById("status-list");
  const resultsEl = document.getElementById("search-results");
  const sectionsEl = document.getElementById("managed-sections");
  const searchInput = document.getElementById("portal-search");

  metaEl.textContent = `Generated ${data.generated_at} · Docs root: ${data.docs_root}`;

  (data.status.sections || []).forEach((section) => {
    const li = document.createElement("li");
    li.className = "status-item";
    const status = section.status || "unknown";
    li.innerHTML = `<strong>${section.name}</strong><span>Status: ${status}${section.target ? ` · ${section.target}` : ""}</span>`;
    statusList.appendChild(li);
  });

  const renderMarkdown = (markdown) => window.snarkdown ? window.snarkdown(markdown) : `<pre>${markdown}</pre>`;

  (data.sections || []).forEach((section) => {
    const article = document.createElement("article");
    article.id = `section-${section.id}`;
    const heading = document.createElement("h3");
    heading.textContent = section.title;
    const meta = document.createElement("div");
    meta.className = "section-meta";
    meta.textContent = `Source: ${section.source}`;
    const content = document.createElement("div");
    content.className = "section-content";
    content.innerHTML = renderMarkdown(section.markdown);
    article.appendChild(heading);
    article.appendChild(meta);
    article.appendChild(content);
    sectionsEl.appendChild(article);
  });

  const inventory = data.inventory || [];

  function renderResults(items) {
    resultsEl.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("li");
      empty.textContent = "Ничего не найдено. Попробуйте другую формулировку.";
      resultsEl.appendChild(empty);
      return;
    }
    items.slice(0, 30).forEach((item) => {
      const li = document.createElement("li");
      li.className = "search-hit";
      const title = document.createElement("h3");
      title.textContent = `${item.kind.toUpperCase()} · ${item.title}`;
      const summary = document.createElement("p");
      summary.textContent = item.summary;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${item.path} · ${item.modified_at}`;
      li.appendChild(title);
      li.appendChild(summary);
      li.appendChild(meta);
      resultsEl.appendChild(li);
    });
  }

  function normalise(text) {
    return (text || "").toLowerCase();
  }

  const initialTop = inventory.slice(0, 8);
  renderResults(initialTop);

  searchInput.addEventListener("input", (event) => {
    const query = normalise(event.target.value);
    if (!query) {
      renderResults(initialTop);
      return;
    }
    const results = inventory.filter((item) => {
      const haystack = [
        item.title,
        item.summary,
        item.path,
        ...(item.tags || []),
      ]
        .map(normalise)
        .join(" ");
      return haystack.includes(query);
    });
    renderResults(results);
  });
})();
""".strip()

_SNARKDOWN_JS = """/*!
 * snarkdown v2.0.0
 * The MIT License (MIT)
 * Copyright (c) 2017 Jason Miller
 * Source: https://github.com/developit/snarkdown
 */
!function(e,n){"object"==typeof exports&&"undefined"!=typeof module?module.exports=n():"function"==typeof define&&define.amd?define(n):(e=e||self).snarkdown=n()}(this,function(){var e={"":["<em>","</em>"],_:["<strong>","</strong>"],"*":["<strong>","</strong>"],"~":["<s>","</s>"],"\n":["<br />"]," ":["<br />"],"-":["<hr />"]};function n(e){return e.replace(RegExp("^"+(e.match(/^(\t| )+/)||"")[0],"gm"),"")}function r(e){return(e+"").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}return function t(o,a){var c,s,l,g,u,p=/((?:^|\n+)(?:\n---+|\* \*(?: \*)+)\n)|(?:^``` *(\w*)\n([\s\S]*?)\n```$)|((?:(?:^|\n+)(?:\t|  {2,}).+)+\n*)|((?:(?:^|\n)([>*+-]|\d+\.)\s+.*)+)|(?:!\[([^\]]*?)\]\(([^)]+?)\))|(\[)|(\](?:\(([^)]+?)\))?)|(?:(?:^|\n+)([^\s].*)\n(-{3,}|={3,})(?:\n+|$))|(?:(?:^|\n+)(#{1,6})\s*(.+)(?:\n+|$))|(?:`([^`].*?)`)|(  \n\n*|\n{2,}|__|\*\*|[_*]|~~)/gm,f=[],i="",d=a||{},m=0;function h(n){var r=e[n[1]||""],t=f[f.length-1]==n;return r?r[1]?(t?f.pop():f.push(n),r[0|t]):r[0]:n}function $(){for(var e="";f.length;)e+=h(f[f.length-1]);return e}for(o=o.replace(/^\[(.+?)\]:\s*(.+)$/gm,function(e,n,r){return d[n.toLowerCase()]=r,""}).replace(/^\n+|\n+$/g,"");l=p.exec(o);)s=o.substring(m,l.index),m=p.lastIndex,c=l[0],s.match(/[^\\](\\\\)*\\$/)||((u=l[3]||l[4])?c='<pre class="code '+(l[4]?"poetry":l[2].toLowerCase())+'"><code'+(l[2]?' class="language-'+l[2].toLowerCase()+'"':"")+">"+n(r(u).replace(/^\n+|\n+$/g,""))+"</code></pre>":(u=l[6])?(u.match(/\./)&&(l[5]=l[5].replace(/^\d+/gm,"")),g=t(n(l[5].replace(/^\s*[>*+.-]/gm,""))),">"==u?u="blockquote":(u=u.match(/\./)?"ol":"ul",g=g.replace(/^(.*)(\n|$)/gm,"<li>$1</li>")),c="<"+u+">"+g+"</"+u+">"):l[8]?c='<img src="'+r(l[8])+'" alt="'+r(l[7])+'">':l[10]?(i=i.replace("<a>",'<a href="'+r(l[11]||d[s.toLowerCase()])+'">'),c=$()+"</a>"):l[9]?c="<a>":l[12]||l[14]?c="<"+(u="h"+(l[14]?l[14].length:l[13]>"="?1:2))+">"+t(l[12]||l[15],d)+"</"+u+">":l[16]?c="<code>"+r(l[16])+"</code>":(l[17]||l[1])&&(c=h(l[17]||"--"))),i+=s,i+=c;return(i+o.substring(m)+$()).replace(/^\n+|\n+$/g,"")}});
"""


__all__ = ["DocsPortalGenerator", "DocsPortalResult", "DocsPortalError", "PORTAL_DEFAULT_BUDGET"]
