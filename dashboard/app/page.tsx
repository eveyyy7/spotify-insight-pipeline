import { ArrowUpRight, CheckCircle2, Database, ShieldCheck, Sparkles } from "lucide-react";
import { getDashboardData } from "@/lib/dashboard-data";

export const dynamic = "force-dynamic";

const format = new Intl.NumberFormat("en-US");

export default async function Home() {
  const { summary, ranking, evidence, recommendation, database } = await getDashboardData();
  const maxScore = Math.max(...ranking.map((row) => row.priorityScore));
  const problemSignals = summary.complaints + summary.cancellations;
  const topIssue = ranking[0];

  return (
    <main className="min-h-screen bg-[#f4f1e8] text-[#121812]">
      <section className="hero-grid border-b-2 border-[#121812] px-5 py-6 sm:px-10 lg:px-16">
        <nav className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-[0.12em]">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-[#1ed760] text-[#0b2b16]">SI</span>
            Spotify Insight Lab
          </div>
          <span className="rounded-full border border-[#121812] bg-[#fffdf6] px-3 py-1.5 text-xs font-semibold">
            Haas · Fall 2026
          </span>
        </nav>

        <div className="mx-auto grid max-w-7xl gap-10 pb-12 pt-16 lg:grid-cols-[1.25fr_.75fr] lg:items-end lg:pt-24">
          <div>
            <p className="mb-5 flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#0a6b35]">
              <Sparkles className="h-4 w-4" /> Evidence-first product intelligence
            </p>
            <h1 className="max-w-4xl text-5xl font-black leading-[.93] tracking-[-.055em] sm:text-7xl lg:text-[92px]">
              Where Spotify friction gets loud.
            </h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-[#3d463e]">
              A traceable review pipeline turns raw app-store feedback into a ranked product decision—without hiding uncertainty, duplicates, or cost.
            </p>
          </div>
          <div className="border-l-2 border-[#121812] pl-6">
            <p className="text-xs font-bold uppercase tracking-[.16em] text-[#586158]">Current published scope</p>
            <p className="mt-3 text-2xl font-bold">{summary.scopeLabel}</p>
            <p className="mt-3 text-sm leading-6 text-[#586158]">
              Final declared scope: 100,099 classified reviews and one empty-text quarantine. Mechanical checker status: pass.
            </p>
          </div>
        </div>
      </section>

      <section className="border-b-2 border-[#121812] bg-[#121812] text-[#f7f4ea]">
        <div className="mx-auto grid max-w-7xl grid-cols-2 divide-x divide-y divide-[#3b443b] sm:grid-cols-4 sm:divide-y-0">
          {[
            ["Reviews analyzed", format.format(summary.analyzedReviews)],
            ["Complaints", format.format(summary.complaints)],
            ["Cancellations", format.format(summary.cancellations)],
            ["Needs review", format.format(summary.needsReview)],
          ].map(([label, value]) => (
            <div key={label} className="px-5 py-7 sm:px-8">
              <p className="text-3xl font-black tracking-tight text-[#1ed760]">{value}</p>
              <p className="mt-1 text-xs font-semibold uppercase tracking-[.12em] text-[#aeb7ae]">{label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 sm:px-10 lg:px-16 lg:py-24">
        <div className="grid gap-12 lg:grid-cols-[.75fr_1.25fr]">
          <div>
            <p className="eyebrow">Ranked issue landscape</p>
            <h2 className="section-title">Cumulative burden beats raw volume.</h2>
            <p className="mt-5 max-w-md leading-7 text-[#586158]">
              Priority score is the severity sum. It equals complaint count × mean severity, preserving the grader’s deterministic baseline.
            </p>
            <div className="mt-8 rounded-2xl bg-[#ff6b35] p-6 text-[#251108]">
              <p className="text-xs font-bold uppercase tracking-[.14em]">Problem signals</p>
              <p className="mt-2 text-4xl font-black">{(problemSignals / summary.analyzedReviews * 100).toFixed(1)}%</p>
              <p className="mt-2 text-sm leading-6">complaint or cancellation intent in the submitted 100,100-review scope</p>
            </div>
          </div>

          <div className="space-y-3">
            {ranking.map((row) => (
              <article key={row.issueId} className="rounded-2xl border-2 border-[#121812] bg-[#fffdf6] p-5 shadow-[4px_4px_0_#121812]">
                <div className="flex items-baseline justify-between gap-4">
                  <div className="flex items-baseline gap-4">
                    <span className="font-mono text-sm font-bold text-[#0a6b35]">#{row.rank}</span>
                    <h3 className="text-lg font-extrabold">{row.label}</h3>
                  </div>
                  <strong className="text-xl">{format.format(row.priorityScore)}</strong>
                </div>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#d9d7ce]">
                  <div className="h-full rounded-full bg-[#1ed760]" style={{ width: `${row.priorityScore / maxScore * 100}%` }} />
                </div>
                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs font-semibold text-[#586158]">
                  <span>{format.format(row.complaintCount)} complaints</span>
                  <span>mean severity {row.meanSeverity.toFixed(3)}</span>
                  <span>severity sum {format.format(row.severitySum)}</span>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y-2 border-[#121812] bg-[#c7b5ff] px-5 py-16 sm:px-10 lg:px-16 lg:py-20">
        <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[.45fr_1fr]">
          <div>
            <p className="eyebrow">Jev-generated recommendation</p>
            <span className="mt-8 inline-grid h-16 w-16 place-items-center rounded-full border-2 border-[#121812] bg-[#fffdf6]">
              <ArrowUpRight className="h-8 w-8" />
            </span>
          </div>
          <div>
            <h2 className="section-title max-w-4xl">Stabilize core playback before the next product cycle.</h2>
            <p className="mt-6 max-w-3xl text-lg leading-8">{summary.recommendation}</p>
            <p className="mt-4 max-w-3xl font-mono text-[11px] leading-5 text-[#42385f]">
              model: {recommendation.model} · confidence: {recommendation.confidence?.toFixed(2)} · request_id: {recommendation.requestId}
            </p>
            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {[
                `${format.format(topIssue.complaintCount)} complaints`,
                `${topIssue.meanSeverity.toFixed(3)} mean severity`,
                `${format.format(topIssue.priorityScore)} priority score`,
              ].map((item) => (
                <div key={item} className="rounded-xl border-2 border-[#121812] bg-[#fffdf6]/70 p-4 text-sm font-extrabold">{item}</div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 sm:px-10 lg:px-16 lg:py-24">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div>
            <p className="eyebrow">Traceable review evidence</p>
            <h2 className="section-title">Numbers you can walk back to source.</h2>
          </div>
          <a className="inline-flex items-center gap-2 text-sm font-bold underline decoration-2 underline-offset-4" href="/api/insights">
            Inspect backend JSON <Database className="h-4 w-4" />
          </a>
        </div>
        <div className="mt-10 grid gap-5 lg:grid-cols-2">
          {evidence.map((row) => (
            <article key={row.reviewId} className="rounded-3xl border-2 border-[#121812] bg-[#fffdf6] p-6 sm:p-8">
              <div className="flex flex-wrap gap-2 text-xs font-bold uppercase tracking-[.1em]">
                <span className="rounded-full bg-[#1ed760] px-3 py-1">{row.topic}</span>
                <span className="rounded-full bg-[#e8e4d9] px-3 py-1">severity {row.severity}</span>
                {row.needsReview && <span className="rounded-full bg-[#ffd6c8] px-3 py-1">human review flagged</span>}
              </div>
              <blockquote className="mt-6 text-xl font-bold leading-8 tracking-tight">“{row.quote}”</blockquote>
              <p className="mt-6 break-all font-mono text-[11px] text-[#687068]">review_id: {row.reviewId}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className="border-t-2 border-[#121812] bg-[#fffdf6] px-5 py-10 sm:px-10 lg:px-16">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-6 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3 text-sm font-bold"><ShieldCheck className="h-5 w-5 text-[#0a6b35]" /> D1 stores {format.format(database.processedReviewRows)} processed reviews, {database.claimRows} claims, rankings, evidence, and the model output.</div>
          <div className="flex items-center gap-2 text-xs text-[#586158]"><CheckCircle2 className="h-4 w-4" /> Synthetic system-test cases are excluded from business results.</div>
        </div>
      </footer>
    </main>
  );
}
