import { integer, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const datasetSummary = sqliteTable("dataset_summary", {
  id: text("id").primaryKey(),
  scopeLabel: text("scope_label").notNull(),
  analyzedReviews: integer("analyzed_reviews").notNull(),
  complaints: integer("complaints").notNull(),
  cancellations: integer("cancellations").notNull(),
  needsReview: integer("needs_review").notNull(),
  recommendation: text("recommendation").notNull(),
  refreshedAt: text("refreshed_at").notNull(),
});

export const issueRankings = sqliteTable("issue_rankings", {
  issueId: text("issue_id").primaryKey(),
  rank: integer("rank").notNull(),
  label: text("label").notNull(),
  complaintCount: integer("complaint_count").notNull(),
  meanSeverity: real("mean_severity").notNull(),
  severitySum: integer("severity_sum").notNull(),
  priorityScore: integer("priority_score").notNull(),
});

export const reviewEvidence = sqliteTable("review_evidence", {
  reviewId: text("review_id").primaryKey(),
  issueId: text("issue_id").notNull(),
  topic: text("topic").notNull(),
  intent: text("intent").notNull(),
  severity: integer("severity").notNull(),
  quote: text("quote").notNull(),
  needsReview: integer("needs_review", { mode: "boolean" }).notNull(),
});

export const datasetImports = sqliteTable("dataset_imports", {
  id: text("id").primaryKey(),
  sourceDigest: text("source_digest").notNull(),
  importedAt: text("imported_at").notNull(),
});

export const processedReviews = sqliteTable("processed_reviews", {
  reviewId: text("review_id").primaryKey(),
  sourceSha256: text("source_sha256").notNull(),
  topic: text("topic").notNull(),
  intent: text("intent").notNull(),
  severity: integer("severity").notNull(),
  sentiment: real("sentiment").notNull(),
  evidenceQuote: text("evidence_quote").notNull(),
  needsReview: integer("needs_review", { mode: "boolean" }).notNull(),
  labelConfig: text("label_config").notNull(),
});

export const claimRecords = sqliteTable("claim_records", {
  claimId: text("claim_id").primaryKey(),
  issueId: text("issue_id").notNull(),
  metric: text("metric").notNull(),
  value: text("value").notNull(),
});

export const analysisOutputs = sqliteTable("analysis_outputs", {
  id: text("id").primaryKey(),
  outputType: text("output_type").notNull(),
  text: text("text").notNull(),
  model: text("model").notNull(),
  requestId: text("request_id").notNull(),
  confidence: real("confidence"),
  sourceDigest: text("source_digest").notNull(),
  createdAt: text("created_at").notNull(),
});

export const modelCalls = sqliteTable("model_calls", {
  requestId: text("request_id").primaryKey(),
  role: text("role").notNull(),
  model: text("model").notNull(),
  outcome: text("outcome").notNull(),
  labelConfig: text("label_config").notNull(),
  inputTokens: integer("input_tokens").notNull(),
  outputTokens: integer("output_tokens").notNull(),
  runtimeSeconds: real("runtime_seconds").notNull(),
  stateSha256: text("state_sha256").notNull(),
  answer: text("answer").notNull(),
  confidence: real("confidence"),
  createdAt: text("created_at").notNull(),
});
