import { asc, eq } from "drizzle-orm";
import { getDb } from "@/db";
import { datasetSummary, issueRankings, reviewEvidence } from "@/db/schema";

const summarySeed = {
  id: "development-10000-v1",
  scopeLabel: "10,000-review development checkpoint",
  analyzedReviews: 10_000,
  complaints: 4_239,
  cancellations: 391,
  needsReview: 3_074,
  recommendation:
    "Test a less restrictive free-tier control model around song selection, queue management, repeat, skip/previous, and seeking—while protecting Premium conversion with explicit guardrails.",
  refreshedAt: "2026-10-13T22:00:00-07:00",
};

const rankingSeed = [
  ["free_tier_premium_gating", 1, "Free-tier / Premium gating", 833, 2.97, 2474],
  ["playback_reliability", 2, "Playback reliability", 345, 3.539, 1221],
  ["ads_experience", 3, "Ads experience", 520, 2.29, 1191],
  ["product_regression_ui", 4, "Product regression & UI", 351, 2.772, 973],
  ["other_remaining_issues", 5, "Other remaining issues", 237, 2.819, 668],
  ["account_access", 6, "Account access", 152, 3.914, 595],
  ["playback_content_control", 7, "Playback content control", 153, 3.399, 520],
  ["billing_account", 8, "Billing account", 49, 3.673, 180],
] as const;

const evidenceSeed = [
  {
    reviewId: "66c56c76-ca94-46ef-b0a1-931654ead16d",
    issueId: "free_tier_premium_gating",
    topic: "billing",
    intent: "complaint",
    severity: 4,
    quote:
      "Wanted this so I could listen to Doctor Who audio dramas at work, found out it was basically impossible to play the tracks in their intended order without premium. Ads I can accept, but locking basic functionality behind a paywall is vile.",
    needsReview: true,
  },
  {
    reviewId: "b20076f5-ef36-4e8f-9ceb-3bb031d16353",
    issueId: "free_tier_premium_gating",
    topic: "billing",
    intent: "complaint",
    severity: 4,
    quote:
      "I can't choose the songs I want to play. Has to be a premium subscription for that, the most basic thing to do. No thanks!",
    needsReview: true,
  },
] as const;

export async function getDashboardData() {
  const db = getDb();
  await db.insert(datasetSummary).values(summarySeed).onConflictDoNothing();
  await db.insert(issueRankings).values(
    rankingSeed.map(([issueId, rank, label, complaintCount, meanSeverity, severitySum]) => ({
      issueId,
      rank,
      label,
      complaintCount,
      meanSeverity,
      severitySum,
      priorityScore: severitySum,
    })),
  ).onConflictDoNothing();
  await db.insert(reviewEvidence).values([...evidenceSeed]).onConflictDoNothing();

  const [summary] = await db.select().from(datasetSummary).where(eq(datasetSummary.id, summarySeed.id));
  const ranking = await db.select().from(issueRankings).orderBy(asc(issueRankings.rank));
  const evidence = await db.select().from(reviewEvidence);
  return { summary, ranking, evidence };
}
