CREATE TABLE `dataset_summary` (
	`id` text PRIMARY KEY NOT NULL,
	`scope_label` text NOT NULL,
	`analyzed_reviews` integer NOT NULL,
	`complaints` integer NOT NULL,
	`cancellations` integer NOT NULL,
	`needs_review` integer NOT NULL,
	`recommendation` text NOT NULL,
	`refreshed_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `issue_rankings` (
	`issue_id` text PRIMARY KEY NOT NULL,
	`rank` integer NOT NULL,
	`label` text NOT NULL,
	`complaint_count` integer NOT NULL,
	`mean_severity` real NOT NULL,
	`severity_sum` integer NOT NULL,
	`priority_score` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `review_evidence` (
	`review_id` text PRIMARY KEY NOT NULL,
	`issue_id` text NOT NULL,
	`topic` text NOT NULL,
	`intent` text NOT NULL,
	`severity` integer NOT NULL,
	`quote` text NOT NULL,
	`needs_review` integer NOT NULL
);
