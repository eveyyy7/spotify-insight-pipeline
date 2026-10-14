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
