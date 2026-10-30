"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_BASE || "";
type Issue = { id: number; period: string; title: string; created_at: number };

export default function NewslettersPage() {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!API) { setErr("No backend configured (NEXT_PUBLIC_API_BASE)."); return; }
    fetch(`${API}/newsletters`).then((r) => r.json())
      .then((j) => setIssues(Array.isArray(j) ? j : []))
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <main>
      <h1>Monthly newsletters</h1>
      <div className="sub">Short retrospectives of last month&apos;s solar wind
        and space weather, written by an LLM from fixed open-data packages
        (DONKI, Kyoto Dst, GFZ Kp, OMNI). Published on the 1st.</div>
      {err && <p className="err">{err}</p>}
      {issues.length === 0 && !err && <p className="muted">No issues yet.</p>}
      {issues.map((i) => (
        <Link key={i.id} href={`/newsletters/${i.id}`} className="nl-item">
          <strong>{i.period}</strong> — {i.title}
        </Link>
      ))}
    </main>
  );
}
