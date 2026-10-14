import { asc, eq, inArray } from "drizzle-orm";
import { getDb } from "@/db";
import { datasetSummary, issueRankings, reviewEvidence } from "@/db/schema";

const summarySeed = {
  id: "final-100100-v1",
  scopeLabel: "100,100-review final analysis scope",
  analyzedReviews: 100_100,
  complaints: 29_986,
  cancellations: 1_596,
  needsReview: 22_365,
  recommendation:
    "Prioritize playback reliability in the next product cycle: reduce crashes and unexpected stops, prevent unwanted track substitution, and make failure-to-start states diagnosable and recoverable.",
  refreshedAt: "2026-10-14T04:04:00-07:00",
};

const rankingSeed = [
  ["topic:playback", 1, "Playback", 8683, 3.568467, 30985],
  ["topic:usability", 2, "Usability", 10514, 2.694217, 28327],
  ["topic:catalog", 3, "Catalog", 3132, 3.069923, 9615],
  ["topic:billing", 4, "Billing", 2565, 3.078363, 7896],
  ["topic:other", 5, "Other", 3344, 2.197368, 7348],
  ["topic:access", 6, "Access", 1731, 3.931254, 6805],
  ["topic:downloads", 7, "Downloads", 1515, 3.622442, 5488],
  ["topic:support", 8, "Support", 98, 2.897959, 284],
] as const;

const evidenceSeed = [
  {
    reviewId: "a6eee2f8-ce5b-4686-a1f4-2c90c159bdd2",
    issueId: "topic:playback",
    topic: "playback",
    intent: "complaint",
    severity: 4,
    quote:
      "If the free version is constantly crashing, why the hell would I ever pay for premium service?!? It will play 1 or 2 songs then stop. I tried clearing the cache, uninstalling/reinstalling, adjusted the data mode, and signed in/out with no change.",
    needsReview: true,
  },
  {
    reviewId: "b3da207e-888d-40bd-bd5d-11f376f5eeda",
    issueId: "topic:playback",
    topic: "playback",
    intent: "complaint",
    severity: 4,
    quote:
      "Every time I play my favorite song, it plays another song and I hate it.",
    needsReview: true,
  },
] as const;

export async function getDashboardData() {
  const db = getDb();
  await db.insert(datasetSummary).values(summarySeed).onConflictDoUpdate({
    target: datasetSummary.id,
    set: summarySeed,
  });
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
  const rankingIds = rankingSeed.map(([issueId]) => issueId);
  const evidenceIds = evidenceSeed.map((row) => row.reviewId);
  const ranking = await db.select().from(issueRankings)
    .where(inArray(issueRankings.issueId, rankingIds)).orderBy(asc(issueRankings.rank));
  const evidence = await db.select().from(reviewEvidence)
    .where(inArray(reviewEvidence.reviewId, evidenceIds));
  return { summary, ranking, evidence };
}
