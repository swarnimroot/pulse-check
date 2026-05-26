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
  tombstoned_at: string | null;
  tombstone_reason: string | null;
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
  // Highest brief_id for an A1 brief (scope_type=aspect_1_sku) on this
  // product, or null when no brief has been generated yet. Standalone uses
  // this to fetch /api/brief/:id directly without a sibling lookup endpoint.
  latest_brief_id: number | null;
}

export interface Claim {
  // `header` is a 2-5 word bold lead-in shown ahead of `claim_text` (added in
  // prompt_version a1_brief_v2). Optional: older briefs in storage lack it
  // and the UI renders without the lead-in in that case.
  header?: string;
  claim_text: string;
  cited_mention_ids: string[];
}

export interface BriefSection {
  heading: string;
  claims: Claim[];
}

// Added in a1_brief_v3 (session 41). Briefs persisted under v2 and earlier
// lack this field; consumers check for presence before rendering.
export interface BriefSummary {
  text: string;
  cited_mention_ids: string[];
}

export interface BriefNarrative {
  brief_title: string;
  sections: BriefSection[];
  summary?: BriefSummary | null;
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

// /api/compare — cross-product heatmap payload (bite 32.a).
export interface CompareCell {
  aspect: string;
  total_mentions: number;
  net_sentiment: number;
  mention_ids: string[];
}

export interface CompareProductRow {
  product_id: string;
  display_name: string;
  brand: string;
  cells: CompareCell[];
}

export interface CompareResponse {
  products: CompareProductRow[];
  aspects: string[];
  run_id: string | null;
  generated_at: string;
}

// /api/home — home-page summary + plain-English pipeline explainer (bite 32.b).
export interface PipelineStageStat {
  key: string;
  label: string;
  title: string;
  description: string;
  ai: boolean;
  chips: { name: string; value: string | number }[];
}

export interface HomeSummary {
  run_id: string | null;
  products_tracked: number;
  mentions_analyzed: number;
  pipeline: PipelineStageStat[];
  generated_at: string;
}

// /api/pair — head-to-head aspect scorecard (bite 32.b).
export interface PairAspectCell {
  total_mentions: number;
  net_sentiment: number;
  mention_ids: string[];
}

export interface PairAspectRow {
  aspect: string;
  primary: PairAspectCell | null;
  competitor: PairAspectCell | null;
  delta: number;
  leader: "primary" | "competitor" | "tie";
}

export interface PairProductRef {
  product_id: string;
  display_name: string;
  brand: string;
}

export interface PairResponse {
  primary: PairProductRef;
  competitor: PairProductRef;
  aspects: string[];
  rows: PairAspectRow[];
  primary_leads_count: number;
  competitor_leads_count: number;
  ties_count: number;
  run_id: string | null;
  generated_at: string;
}

// /api/sources — operator-curated source list for the home page accordion.
export interface SourceEntry {
  name: string;
  detail: string;
}

export interface SourcesResponse {
  reddit: SourceEntry[];
  youtube: SourceEntry[];
  review_sites: SourceEntry[];
  generated_at: string;
}
