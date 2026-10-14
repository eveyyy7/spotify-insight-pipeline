CREATE TABLE `analysis_outputs` (
	`id` text PRIMARY KEY NOT NULL,
	`output_type` text NOT NULL,
	`text` text NOT NULL,
	`model` text NOT NULL,
	`request_id` text NOT NULL,
	`confidence` real,
	`source_digest` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `claim_records` (
	`claim_id` text PRIMARY KEY NOT NULL,
	`issue_id` text NOT NULL,
	`metric` text NOT NULL,
	`value` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `dataset_imports` (
	`id` text PRIMARY KEY NOT NULL,
	`source_digest` text NOT NULL,
	`imported_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `model_calls` (
	`request_id` text PRIMARY KEY NOT NULL,
	`role` text NOT NULL,
	`model` text NOT NULL,
	`outcome` text NOT NULL,
	`label_config` text NOT NULL,
	`input_tokens` integer NOT NULL,
	`output_tokens` integer NOT NULL,
	`runtime_seconds` real NOT NULL,
	`state_sha256` text NOT NULL,
	`answer` text NOT NULL,
	`confidence` real,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `processed_reviews` (
	`review_id` text PRIMARY KEY NOT NULL,
	`source_sha256` text NOT NULL,
	`topic` text NOT NULL,
	`intent` text NOT NULL,
	`severity` integer NOT NULL,
	`sentiment` real NOT NULL,
	`evidence_quote` text NOT NULL,
	`needs_review` integer NOT NULL,
	`label_config` text NOT NULL
);
