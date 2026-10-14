import { getDashboardData } from "@/lib/dashboard-data";

export const dynamic = "force-dynamic";

export async function GET() {
  const data = await getDashboardData();
  return Response.json({
    status: "ok",
    scope: data.summary.scopeLabel,
    summary: data.summary,
    ranking: data.ranking,
    evidence: data.evidence,
    recommendation: {
      text: data.recommendation.text,
      model: data.recommendation.model,
      requestId: data.recommendation.requestId,
      confidence: data.recommendation.confidence,
      generatedAt: data.recommendation.createdAt,
      stateSha256: data.recommendation.sourceDigest,
      call: data.call,
    },
    database: data.database,
    provenance: {
      rankingFormula: "priority_score = severity_sum = complaint_count × mean_severity",
      source: "saved Assignment 5 final 100,100-review grading artifacts",
      syntheticCasesExcluded: true,
      recommendationSource: "saved Jev model output inferred from ranking and evidence; persisted in D1",
    },
  });
}
