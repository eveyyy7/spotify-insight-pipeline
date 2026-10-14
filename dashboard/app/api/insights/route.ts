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
    provenance: {
      rankingFormula: "priority_score = severity_sum = complaint_count × mean_severity",
      source: "saved Assignment 5 development artifacts",
      syntheticCasesExcluded: true,
    },
  });
}
