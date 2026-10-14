import { asc, count, eq, inArray } from "drizzle-orm";
import { getDb } from "@/db";
import {
  analysisOutputs,
  claimRecords,
  datasetImports,
  datasetSummary,
  issueRankings,
  modelCalls,
  processedReviews,
  reviewEvidence,
} from "@/db/schema";
import dashboardData from "@/data/dashboard-data.json";

const chunks = <T,>(rows: T[], size: number) =>
  Array.from({ length: Math.ceil(rows.length / size) }, (_, index) =>
    rows.slice(index * size, (index + 1) * size),
  );

async function ensureDashboardDataImported() {
  const db = getDb();
  const [existing] = await db
    .select({ id: datasetImports.id })
    .from(datasetImports)
    .where(eq(datasetImports.id, dashboardData.importId));

  if (existing) return;

  // A new source digest is a complete replacement, so stale rows cannot win.
  await db.delete(datasetImports);
  await db.delete(datasetSummary);
  await db.delete(issueRankings);
  await db.delete(reviewEvidence);
  await db.delete(processedReviews);
  await db.delete(claimRecords);
  await db.delete(analysisOutputs);
  await db.delete(modelCalls);

  await db.insert(datasetSummary).values(dashboardData.summary);
  await db.insert(issueRankings).values(dashboardData.ranking);
  await db.insert(reviewEvidence).values(
    dashboardData.evidence.map((row) => ({
      reviewId: row.reviewId,
      issueId: `topic:${row.topic}`,
      topic: row.topic,
      intent: row.intent,
      severity: row.severity,
      quote: row.evidenceQuote,
      needsReview: row.needsReview,
    })),
  );

  // Keep each statement below D1/SQLite's bound-variable ceiling.
  for (const batch of chunks(dashboardData.processedReviews, 10)) {
    await db.insert(processedReviews).values(batch);
  }
  for (const batch of chunks(dashboardData.claims, 10)) {
    await db.insert(claimRecords).values(batch);
  }
  await db.insert(analysisOutputs).values({
    id: dashboardData.recommendation.id,
    outputType: "product_recommendation",
    text: dashboardData.recommendation.text,
    model: dashboardData.recommendation.model,
    requestId: dashboardData.recommendation.requestId,
    confidence: dashboardData.recommendation.confidence,
    sourceDigest: dashboardData.recommendation.stateSha256,
    createdAt: dashboardData.recommendation.createdAt,
  });
  await db.insert(modelCalls).values(dashboardData.modelCall);
  await db.insert(datasetImports).values({
    id: dashboardData.importId,
    sourceDigest: dashboardData.sourceDigest,
    importedAt: dashboardData.recommendation.createdAt,
  });
}

export async function getDashboardData() {
  const db = getDb();
  await ensureDashboardDataImported();

  const [summary] = await db
    .select()
    .from(datasetSummary)
    .where(eq(datasetSummary.id, dashboardData.summary.id));
  const ranking = await db.select().from(issueRankings).orderBy(asc(issueRankings.rank));
  const evidence = await db
    .select()
    .from(reviewEvidence)
    .where(inArray(reviewEvidence.reviewId, dashboardData.evidence.map((row) => row.reviewId)));
  const [recommendation] = await db
    .select()
    .from(analysisOutputs)
    .where(eq(analysisOutputs.id, dashboardData.recommendation.id));
  const [call] = await db
    .select()
    .from(modelCalls)
    .where(eq(modelCalls.requestId, dashboardData.recommendation.requestId));
  const [processedCount] = await db.select({ value: count() }).from(processedReviews);
  const [claimCount] = await db.select({ value: count() }).from(claimRecords);

  return {
    summary: { ...summary, recommendation: recommendation.text },
    ranking,
    evidence,
    recommendation,
    call,
    database: {
      importId: dashboardData.importId,
      sourceDigest: dashboardData.sourceDigest,
      processedReviewRows: processedCount.value,
      claimRows: claimCount.value,
      rankingRows: ranking.length,
      sourcePlaybackProblemRecords: dashboardData.stats.playbackProblemRecords,
    },
  };
}
