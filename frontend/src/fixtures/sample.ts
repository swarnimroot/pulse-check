import type {
  MentionView,
  ProductDetail,
  BriefView,
  AspectRow,
  RunMeta,
} from "@/lib/types";

/**
 * Fixture data for bite 11.2.e visual confirm.
 *
 * Shapes match `pulse_check/api/schemas.py`. 11.3 swaps these for live
 * `/products`, `/product/:id`, `/mentions?ids=`, `/brief/:id` calls.
 */

export const sampleMentions: MentionView[] = [
  {
    mention_id: "m_001",
    source_type: "reddit_post",
    channel: "r/AlienwareOwners",
    author: "u/voidcaster",
    published_at: "2026-04-12T14:23:00Z",
    raw_text:
      "Got the Alienware 16 Aurora last week. The build quality is honestly the best I've felt on a 16-inch chassis in years — magnesium feels solid, no flex on the keyboard deck, hinge is tight. Display is crisp at QHD+ and the colors out of the box are surprisingly accurate for a gaming panel.",
    url: "https://reddit.com/r/AlienwareOwners/comments/x1",
    verified: false,
    upvotes: 142,
    rating: null,
    aspect_tags: [{ aspect: "build_quality", polarity: "positive", intensity: "high" }],
  },
  {
    mention_id: "m_002",
    source_type: "reddit_post",
    channel: "r/GamingLaptops",
    author: "u/thermal_throttle",
    published_at: "2026-04-08T09:11:00Z",
    raw_text:
      "Fans on the Aurora 16 are loud under sustained load. Not deal-breaker loud but you'll want headphones for anything beyond casual play. Comparable to ROG Strix in dB but the pitch is whinier.",
    url: "https://reddit.com/r/GamingLaptops/comments/x2",
    verified: false,
    upvotes: 87,
    rating: null,
    aspect_tags: [{ aspect: "thermals_noise", polarity: "negative", intensity: "medium" }],
  },
  {
    mention_id: "m_003",
    source_type: "bestbuy_review",
    channel: "bestbuy.com",
    author: "Mike R.",
    published_at: "2026-03-28T00:00:00Z",
    raw_text:
      "Battery life is what you'd expect — about 4 hours of light productivity, two if you're gaming. Power brick is brick-sized. Not a portability play.",
    url: "https://bestbuy.com/site/reviews/alienware-16-aurora",
    verified: true,
    upvotes: null,
    rating: 4,
    aspect_tags: [{ aspect: "battery", polarity: "negative", intensity: "low" }],
  },
  {
    mention_id: "m_004",
    source_type: "amazon_review",
    channel: "amazon.com",
    author: "G. Patel",
    published_at: "2026-04-02T00:00:00Z",
    raw_text:
      "Keyboard is a highlight — 1.8mm travel feels great for both gaming and writing, per-key RGB is well diffused. Trackpad is also unusually good for a gaming laptop.",
    url: "https://amazon.com/reviews/alienware-16-aurora",
    verified: true,
    upvotes: null,
    rating: 5,
    aspect_tags: [{ aspect: "keyboard_trackpad", polarity: "positive", intensity: "high" }],
  },
  {
    mention_id: "m_005",
    source_type: "youtube",
    channel: "Hardware Canucks",
    author: "@HardwareCanucks",
    published_at: "2026-03-15T18:00:00Z",
    raw_text:
      "Performance is right where it should be — RTX 4080 mobile pulls 175W sustained, CPU holds boost clocks under combined load. Nothing surprising, but nothing concerning either.",
    url: "https://youtube.com/watch?v=abc123",
    verified: false,
    upvotes: null,
    rating: null,
    aspect_tags: [{ aspect: "performance", polarity: "positive", intensity: "medium" }],
  },
  {
    mention_id: "m_006",
    source_type: "article",
    channel: "Notebookcheck",
    author: "Allen Ngo",
    published_at: "2026-03-22T10:00:00Z",
    raw_text:
      "The display is excellent: 1600p at 240Hz, 100% DCI-P3 coverage measured, peak brightness 487 nits. One of the better gaming-class panels we've measured this cycle.",
    url: "https://notebookcheck.com/alienware-16-aurora",
    verified: false,
    upvotes: null,
    rating: null,
    aspect_tags: [{ aspect: "display", polarity: "positive", intensity: "high" }],
  },
  {
    mention_id: "m_007",
    source_type: "reddit_post",
    channel: "r/Alienware",
    author: "u/qa_failed",
    published_at: "2026-04-19T22:14:00Z",
    raw_text:
      "Three weeks in and the right speaker started rattling at mid-volume. Returned to BB, they swapped the unit. Hopefully an isolated build-QC slip and not a pattern.",
    url: "https://reddit.com/r/Alienware/comments/x7",
    verified: false,
    upvotes: 23,
    rating: null,
    aspect_tags: [{ aspect: "build_quality", polarity: "negative", intensity: "low" }],
  },
  {
    mention_id: "m_008",
    source_type: "amazon_review",
    channel: "amazon.com",
    author: "T. Liu",
    published_at: "2026-04-05T00:00:00Z",
    raw_text:
      "Software is the rough edge. Alienware Command Center is fine when it works but crashes on profile-switch every other day. Dell support docs aren't current either.",
    url: "https://amazon.com/reviews/alienware-16-aurora-2",
    verified: true,
    upvotes: null,
    rating: 3,
    aspect_tags: [{ aspect: "software", polarity: "negative", intensity: "medium" }],
  },
  {
    mention_id: "m_009",
    source_type: "bestbuy_review",
    channel: "bestbuy.com",
    author: "Anonymous",
    published_at: "2026-04-15T00:00:00Z",
    raw_text:
      "For $2,800 it's competitive on paper but you can spec a Strix Scar with the same GPU+CPU for $300 less. The Aurora's design is tighter, though, if that's worth the premium to you.",
    url: "https://bestbuy.com/site/reviews/alienware-16-aurora-2",
    verified: true,
    upvotes: null,
    rating: 4,
    aspect_tags: [{ aspect: "value_pricing", polarity: "neutral", intensity: "medium" }],
  },
  {
    mention_id: "m_010",
    source_type: "youtube",
    channel: "Dave2D",
    author: "@Dave2D",
    published_at: "2026-03-08T16:00:00Z",
    raw_text:
      "Port selection is decent — Thunderbolt 4, full HDMI 2.1, three USB-A, SD reader. Notably no microSD this generation, which some content folks will miss.",
    url: "https://youtube.com/watch?v=def456",
    verified: false,
    upvotes: null,
    rating: null,
    aspect_tags: [{ aspect: "ports_io", polarity: "neutral", intensity: "low" }],
  },
  {
    mention_id: "m_011",
    source_type: "article",
    channel: "The Verge",
    author: "Sean Hollister",
    published_at: "2026-02-28T13:00:00Z",
    raw_text:
      "Webcam is 1080p with IR, finally. The shutter is mechanical. These are table-stakes upgrades but Alienware was overdue.",
    url: "https://theverge.com/alienware-16-aurora-review",
    verified: false,
    upvotes: null,
    rating: null,
    aspect_tags: [{ aspect: "webcam_audio", polarity: "positive", intensity: "low" }],
  },
  {
    mention_id: "m_012",
    source_type: "reddit_post",
    channel: "r/SuggestALaptop",
    author: "u/buyer_pending",
    published_at: "2026-04-21T11:30:00Z",
    raw_text:
      "Considering the Aurora 16 vs the Strix G16. Anyone gone Aurora and regretted it on the price? Strix is genuinely $300 less for the same silicon.",
    url: "https://reddit.com/r/SuggestALaptop/comments/x12",
    verified: false,
    upvotes: 64,
    rating: null,
    aspect_tags: [{ aspect: "value_pricing", polarity: "negative", intensity: "medium" }],
  },
];

export const sampleAspectRows: AspectRow[] = [
  {
    aspect: "build_quality",
    total_mentions: 47,
    net_sentiment: 0.62,
    intensity_counts: { high: 18, medium: 22, low: 7 },
    verified_pct: 38.3,
    sources: ["reddit_post", "bestbuy_review", "amazon_review", "youtube", "article"],
    mention_ids: ["m_001", "m_007"],
    total_mentions_secondary: 12,
    net_sentiment_secondary: 0.41,
    intensity_counts_secondary: { high: 3, medium: 6, low: 3 },
    verified_pct_secondary: 25.0,
    sources_secondary: ["reddit_post", "amazon_review"],
    mention_ids_secondary: [],
  },
  {
    aspect: "display",
    total_mentions: 38,
    net_sentiment: 0.78,
    intensity_counts: { high: 22, medium: 12, low: 4 },
    verified_pct: 42.1,
    sources: ["reddit_post", "youtube", "article", "amazon_review"],
    mention_ids: ["m_006"],
    total_mentions_secondary: 8,
    net_sentiment_secondary: 0.5,
    intensity_counts_secondary: { high: 2, medium: 4, low: 2 },
    verified_pct_secondary: 12.5,
    sources_secondary: ["youtube", "article"],
    mention_ids_secondary: [],
  },
  {
    aspect: "performance",
    total_mentions: 52,
    net_sentiment: 0.34,
    intensity_counts: { high: 12, medium: 28, low: 12 },
    verified_pct: 28.8,
    sources: ["reddit_post", "youtube", "article", "amazon_review", "bestbuy_review"],
    mention_ids: ["m_005"],
    total_mentions_secondary: 19,
    net_sentiment_secondary: 0.21,
    intensity_counts_secondary: { high: 4, medium: 11, low: 4 },
    verified_pct_secondary: 21.0,
    sources_secondary: ["reddit_post", "youtube", "article"],
    mention_ids_secondary: [],
  },
  {
    aspect: "thermals_noise",
    total_mentions: 41,
    net_sentiment: -0.45,
    intensity_counts: { high: 8, medium: 24, low: 9 },
    verified_pct: 31.7,
    sources: ["reddit_post", "youtube", "amazon_review", "bestbuy_review"],
    mention_ids: ["m_002"],
    total_mentions_secondary: 14,
    net_sentiment_secondary: -0.28,
    intensity_counts_secondary: { high: 2, medium: 8, low: 4 },
    verified_pct_secondary: 35.7,
    sources_secondary: ["reddit_post", "amazon_review"],
    mention_ids_secondary: [],
  },
  {
    aspect: "battery",
    total_mentions: 29,
    net_sentiment: -0.55,
    intensity_counts: { high: 5, medium: 11, low: 13 },
    verified_pct: 51.7,
    sources: ["bestbuy_review", "amazon_review", "youtube", "article"],
    mention_ids: ["m_003"],
    total_mentions_secondary: 6,
    net_sentiment_secondary: -0.33,
    intensity_counts_secondary: { high: 1, medium: 2, low: 3 },
    verified_pct_secondary: 33.3,
    sources_secondary: ["bestbuy_review", "amazon_review"],
    mention_ids_secondary: [],
  },
  {
    aspect: "value_pricing",
    total_mentions: 33,
    net_sentiment: -0.18,
    intensity_counts: { high: 6, medium: 15, low: 12 },
    verified_pct: 24.2,
    sources: ["reddit_post", "bestbuy_review", "amazon_review", "article"],
    mention_ids: ["m_009", "m_012"],
    total_mentions_secondary: 21,
    net_sentiment_secondary: -0.31,
    intensity_counts_secondary: { high: 4, medium: 10, low: 7 },
    verified_pct_secondary: 19.0,
    sources_secondary: ["reddit_post", "youtube", "article"],
    mention_ids_secondary: [],
  },
];

export const sampleRunMeta: RunMeta = {
  total_mentions: 1143,
  window_label: "6-month window",
  last_refreshed: "2026-05-07T18:00:00Z",
};

export const sampleProduct: ProductDetail = {
  product_id: "alienware_16_aurora",
  display_name: "Alienware 16 Aurora",
  brand: "Alienware",
  aliases: ["Aurora 16", "Alienware Aurora 16"],
  aspects: sampleAspectRows,
  run_meta: sampleRunMeta,
};

export const sampleBrief: BriefView = {
  brief_id: 1,
  run_id: "run_2026_05_07",
  scope_type: "product",
  scope_id: "alienware_16_aurora",
  prompt_version: "a1_brief_v1",
  model: "claude-sonnet-4-6",
  generated_at: "2026-05-07T19:14:00Z",
  narrative: {
    brief_title: "Alienware 16 Aurora — what owners and reviewers are saying",
    sections: [
      {
        heading: "What's working (PRIMARY)",
        claims: [
          {
            claim_text:
              "Build quality is the standout strength — owners and reviewers cite the magnesium chassis, hinge tightness, and absence of deck flex as best-in-class for a 16-inch gaming laptop.",
            cited_mention_ids: ["m_001"],
          },
          {
            claim_text:
              "Display draws the most enthusiastic positive sentiment of any aspect (net +0.78, 38 mentions) — the QHD+ 240Hz panel measures at 487 nits with full DCI-P3 coverage.",
            cited_mention_ids: ["m_006"],
          },
          {
            claim_text:
              "Keyboard and trackpad receive consistent positive signal across verified retailer reviews; 1.8mm key travel and per-key RGB diffusion are repeatedly singled out.",
            cited_mention_ids: ["m_004"],
          },
        ],
      },
      {
        heading: "What's not working (PRIMARY)",
        claims: [
          {
            claim_text:
              "Thermals and acoustics are a mid-intensity drag — fans run loud under sustained load with a higher-pitched profile than competitors at comparable dB levels.",
            cited_mention_ids: ["m_002"],
          },
          {
            claim_text:
              "Battery life lands in the bottom quartile of mentions (4 hours productivity / 2 hours gaming); 51% of these mentions are verified-purchase reviewers.",
            cited_mention_ids: ["m_003"],
          },
        ],
      },
      {
        heading: "What's working (SECONDARY)",
        claims: [
          {
            claim_text:
              "Performance signal is positive but flat — sustained 175W GPU power and held CPU boost clocks meet expectations without surprising upside.",
            cited_mention_ids: ["m_005"],
          },
        ],
      },
      {
        heading: "What's not working (SECONDARY)",
        claims: [
          {
            claim_text:
              "Software and value-pricing surface as recurring frustrations in cross-referencing mentions — Command Center stability and a $300 price gap to the Strix G16 dominate the negative SECONDARY pool.",
            cited_mention_ids: ["m_008", "m_009", "m_012"],
          },
        ],
      },
    ],
    flagged_citation_issues: {
      fabricated_ids: [],
      out_of_context_ids: [],
      numerical_drift: [],
      empty_claims: [],
    },
  },
};

export const sampleSparklineData = [3, 5, 4, 8, 6, 9, 12, 11, 14, 18, 22, 19, 21, 24, 28, 26, 30, 27, 25, 22, 20, 18, 17, 14, 12, 11];
