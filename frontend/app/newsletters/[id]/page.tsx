"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE || "";

type Issue = { id: number; period: string; title: string; markdown: string };

function esc(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Minimal renderer for our own controlled markdown (headings, bold, tables). */
function renderMd(md: string) {
  const blocks: string[] = [];
  const lines = md.split("\n");
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (ln.startsWith("|") && i + 1 < lines.length && lines[i + 1].startsWith("|-")) {
      const head = ln.split("|").slice(1, -1).map((c) => `<th>${esc(c.trim())}</th>`).join("");
      const rows: string[] = [];
      i += 2;
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].split("|").slice(1, -1)
          .map((c) => `<td>${esc(c.trim())}</td>`).join("");
        rows.push(`<tr>${cells}</tr>`);
        i += 1;
      }
      blocks.push(`<table><thead><tr>${head}</tr></thead><tbody>${rows.join("")}</tbody></table>`);
      continue;
    }
    if (ln.startsWith("### ")) blocks.push(`<h3>${esc(ln.slice(4))}</h3>`);
    else if (ln.startsWith("## ")) blocks.push(`<h2>${esc(ln.slice(3))}</h2>`);
    else if (ln.startsWith("# ")) blocks.push(`<h1>${esc(ln.slice(2))}</h1>`);
    else if (ln.trim()) {
      blocks.push(`<p>${esc(ln).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/_([^_]+)_/g, "<em>$1</em>")}</p>`);
    }
    i += 1;
  }
  return blocks.join("\n");
}

export default function IssuePage() {
  const params = useParams();
  const [issue, setIssue] = useState<Issue | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!API) { setErr("No backend configured (NEXT_PUBLIC_API_BASE)."); return; }
    fetch(`${API}/newsletters/${params.id}`).then((r) => r.json())
      .then((j) => (j.error ? setErr(j.error) : setIssue(j)))
      .catch((e) => setErr(String(e)));
  }, [params.id]);

  return (
    <main>
      {err && <p className="err">{err}</p>}
      {!issue && !err && <p className="muted">Loading...</p>}
      {issue && (
        <div className="md">
          <div dangerouslySetInnerHTML={{ __html: renderMd(issue.markdown || "") }} />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`${API}/newsletters/${issue.id}/chart.svg`}
            alt={`Daily max Kp chart for ${issue.period}`} />
          <p className="muted">Issue {issue.period}. Sources: DONKI,
            Kyoto WDC, GFZ; OMNI when reachable. Kyoto values are provisional.</p>
        </div>
      )}
    </main>
  );
}
