/**
 * Frontend mirrors of `pulse_check/api/schemas.py`. Kept hand-synced; if a
 * shape diverges in 11.3 wiring, update both sides.
 */

export type Polarity = "positive" | "neutral" | "negative";
export type Intensity = "high" | "medium" | "low";

export interface AspectTag {
  aspect: string;
  polarity: Polarity;
  intensity: Intensity;
}

export interface MentionView {
  mention_id: string;
  source_type: string;
  channel: string | null;
  author: string | null;
  published_at: string | null;
  raw_text: string;
  url: string;
  verified: boolean;
  upvotes: number | null;
  rating: number | null;
  aspect_tags: AspectTag[];
}

export interface AspectRow {
  aspect: string;
  total_mentions: number;
  net_sentiment: number;
  intensity_counts: Partial<Record<Intensity, number>>;
  verified_pct: number;
  sources: string[];
  mention_ids: string[];
  total_mentions_secondary: number;
  net_sentiment_secondary: number;
  intensity_counts_secondary: Partial<Record<Intensity, number>>;
  verified_pct_secondary: number;
  sources_secondary: string[];
  mention_ids_secondary: string[];
}

export interface RunMeta {
  total_mentions: number;
  window_label: string;
  last_refreshed: string;
}

export interface ProductSummary {
  product_id: string;
  display_name: string;
  brand: string;
  aliases: string[];
}

export interface ProductDetail extends ProductSummary {
  aspects: AspectRow[];
  run_meta: RunMeta;
}

export interface Claim {
  claim_text: string;
  cited_mention_ids: string[];
}

export interface BriefSection {
  heading: string;
  claims: Claim[];
}

export interface BriefNarrative {
  brief_title: string;
  sections: BriefSection[];
  flagged_citation_issues?: Record<string, unknown>;
}

export interface BriefView {
  brief_id: number;
  run_id: string;
  scope_type: string;
  scope_id: string;
  prompt_version: string;
  model: string;
  generated_at: string;
  narrative: BriefNarrative;
}
