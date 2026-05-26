import { forwardRef, useEffect, useMemo, useRef, useState } from "react";
import { X, Download, FileText, Printer } from "lucide-react";
import { api } from "@/lib/api";
import { briefToMarkdown } from "@/lib/exportMarkdown";
import type {
  AspectRow,
  BriefView,
  Claim,
  MentionView,
  ProductDetail,
} from "@/lib/types";

/**
 * BriefExportButton — opens a centered modal previewing a single-page A4
 * one-pager for the currently-loaded standalone brief, with PDF (browser
 * print) and HTML (Blob download) export actions in a toolbar above the
 * sheet.
 *
 * The A4 sheet is intentionally visual rather than a text dump:
 *   - 4 stat tiles at the top (mentions / pos aspects / neg aspects / net)
 *   - 11-aspect snapshot chip row (color-coded by net sentiment)
 *   - Top 3 strengths + top 3 weaknesses (claim headers only, no body
 *     paragraphs, with [n] bracketed cite numbers)
 *   - Compact citations footer
 *
 * Inline styles are used inside the sheet so the HTML download serializes
 * to a self-contained file without needing Tailwind. The print stylesheet
 * (see `frontend/src/index.css` `@media print` block) hides everything but
 * the sheet when `body.printing` is set, so browser print → "Save as PDF"
 * produces a clean A4 file.
 */

interface BriefExportButtonProps {
  brief: BriefView;
  product: ProductDetail;
}

interface ExtractedClaims {
  strengths: Claim[];
  weaknesses: Claim[];
  citedIds: string[];
}

/**
 * Walk the brief's sections and pick the top 3 strengths + top 3
 * weaknesses. Section headings come from Sonnet — we route on keyword
 * (working / strength / positive vs not working / weakness / complaint /
 * negative). Falls back to first-half/second-half split if no headings
 * match the keyword set.
 */
function extractTopClaims(brief: BriefView): ExtractedClaims {
  const sections = brief.narrative.sections;
  const strengthSections: Claim[] = [];
  const weaknessSections: Claim[] = [];
  for (const s of sections) {
    const h = s.heading.toLowerCase();
    const isWeakness =
      h.includes("not working") ||
      h.includes("weakness") ||
      h.includes("complaint") ||
      h.includes("negative");
    const isStrength =
      !isWeakness &&
      (h.includes("strength") || h.includes("working") || h.includes("positive"));
    if (isWeakness) weaknessSections.push(...s.claims);
    else if (isStrength) strengthSections.push(...s.claims);
  }

  // Fallback: if no headings matched, split sections in half.
  if (strengthSections.length === 0 && weaknessSections.length === 0) {
    const mid = Math.ceil(sections.length / 2);
    for (let i = 0; i < sections.length; i++) {
      if (i < mid) strengthSections.push(...sections[i].claims);
      else weaknessSections.push(...sections[i].claims);
    }
  }

  const strengths = strengthSections.slice(0, 3);
  const weaknesses = weaknessSections.slice(0, 3);

  // Summary paragraph cites lead the [n] numbering so they get [1], [2], [3]
  // — matches reading order on the sheet (the summary sits above strengths).
  // Then strengths cites, then weaknesses cites, deduplicated keeping first
  // appearance.
  const citedSet = new Set<string>();
  if (brief.narrative.summary) {
    for (const id of brief.narrative.summary.cited_mention_ids) {
      citedSet.add(id);
    }
  }
  for (const c of [...strengths, ...weaknesses]) {
    for (const id of c.cited_mention_ids) citedSet.add(id);
  }
  return { strengths, weaknesses, citedIds: [...citedSet] };
}

/**
 * Bucket an aspect's net sentiment into a 3-tone palette:
 *   pos when net > +0.1, neg when net < -0.1, otherwise neutral.
 * No-data aspects collapse to a fourth gray bucket above.
 */
function sentimentTone(net: number): "pos" | "neg" | "neutral" {
  if (net > 0.1) return "pos";
  if (net < -0.1) return "neg";
  return "neutral";
}

const ASPECT_LABELS: Record<string, string> = {
  thermals: "Thermals",
  performance: "Performance",
  keyboard: "Keyboard",
  display: "Display",
  battery: "Battery",
  build_quality: "Build",
  software_experience: "Software",
  price_value: "Price",
  support_warranty: "Support",
  aesthetics: "Aesthetics",
  portability: "Portability",
};

function aspectLabel(a: string): string {
  return ASPECT_LABELS[a] ?? a;
}

function formatNum(n: number): string {
  return n.toLocaleString("en-US");
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function shortSource(source_type: string, channel: string | null): string {
  if (source_type.startsWith("reddit")) return channel ? `r/${channel}` : "reddit";
  if (source_type === "youtube_chunk") return channel ?? "youtube";
  if (source_type === "article") return channel ?? "article";
  return source_type;
}

export function BriefExportButton({
  brief,
  product,
}: BriefExportButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [mentions, setMentions] = useState<Map<string, MentionView>>(new Map());

  const extracted = useMemo(() => extractTopClaims(brief), [brief]);

  // Fetch the cited mentions when the overlay opens (lazy — never preloaded
  // since most viewers never click Export). Result keyed by mention_id so
  // each claim can resolve its bracketed [n] numbers to a source row.
  useEffect(() => {
    if (!open) return;
    if (extracted.citedIds.length === 0) return;
    let cancelled = false;
    api
      .mentions(extracted.citedIds)
      .then((res) => {
        if (cancelled) return;
        const m = new Map<string, MentionView>();
        for (const x of res.mentions) m.set(x.mention_id, x);
        setMentions(m);
      })
      .catch(() => {
        // citations footer renders without source detail in this case;
        // the bracketed numbers stay correct so the export still parses.
      });
    return () => {
      cancelled = true;
    };
  }, [open, extracted.citedIds]);

  // Escape to close.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const sheetRef = useRef<HTMLDivElement | null>(null);

  const handlePrint = (): void => {
    document.body.classList.add("printing");
    // Allow a tick for the class to apply before opening the print dialog.
    setTimeout(() => {
      window.print();
      document.body.classList.remove("printing");
    }, 30);
  };

  const handleHtmlDownload = (): void => {
    if (!sheetRef.current) return;
    const innerHtml = sheetRef.current.outerHTML;
    const docHtml = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>pulse-check — ${product.display_name}</title>
  <style>
    body { margin: 0; background: #F4F5F7; font-family: Arial, Helvetica, sans-serif; }
    .a4-sheet-wrapper { display: flex; justify-content: center; padding: 24px; }
  </style>
</head>
<body>
  <div class="a4-sheet-wrapper">${innerHtml}</div>
</body>
</html>`;
    const blob = new Blob([docHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pulse-check-${product.product_id}-${new Date().toISOString().slice(0, 10)}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleMarkdownDownload = (): void => {
    // Citation numbers must agree with what the visual sheet renders, so
    // rebuild the same Map<mention_id, n> here from the same citedIds list.
    const citeNumber = new Map<string, number>();
    extracted.citedIds.forEach((id, i) => citeNumber.set(id, i + 1));
    const md = briefToMarkdown({
      product,
      brief,
      strengths: extracted.strengths,
      weaknesses: extracted.weaknesses,
      citedIds: extracted.citedIds,
      citeNumber,
      mentions,
    });
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pulse-check-${product.product_id}-${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="self-start rounded-md border border-accent-soft bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent transition-colors duration-1 ease-aw hover:border-accent hover:bg-accent-soft hover:text-accent-hover"
      >
        Export brief
      </button>
      {open && (
        <ExportOverlay
          onClose={() => setOpen(false)}
          onPrint={handlePrint}
          onHtmlDownload={handleHtmlDownload}
          onMarkdownDownload={handleMarkdownDownload}
        >
          <BriefExportSheet
            ref={sheetRef}
            product={product}
            brief={brief}
            extracted={extracted}
            mentions={mentions}
          />
        </ExportOverlay>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Overlay — full-screen scrim + toolbar + scrollable A4 preview.
// ---------------------------------------------------------------------------

interface ExportOverlayProps {
  onClose: () => void;
  onPrint: () => void;
  onHtmlDownload: () => void;
  onMarkdownDownload: () => void;
  children: React.ReactNode;
}

function ExportOverlay({
  onClose,
  onPrint,
  onHtmlDownload,
  onMarkdownDownload,
  children,
}: ExportOverlayProps): JSX.Element {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Brief export preview"
      className="fixed inset-0 z-50 flex flex-col bg-fg/40 backdrop-blur-md export-overlay"
    >
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border bg-surface px-6 py-3 shadow-card">
        <div className="flex flex-col gap-0.5">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
            Preview · single-page A4 export
          </span>
          <span className="text-xs text-fg-secondary">
            What it looks like as a saved file
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onPrint}
            className="flex items-center gap-2 rounded-md border border-accent bg-accent px-3 py-1.5 text-xs font-medium text-fg-on-accent transition-colors duration-1 ease-aw hover:bg-accent-hover"
          >
            <Printer size={14} aria-hidden="true" />
            Save as PDF
          </button>
          <button
            type="button"
            onClick={onHtmlDownload}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium text-fg-secondary transition-colors duration-1 ease-aw hover:border-accent hover:text-accent"
          >
            <Download size={14} aria-hidden="true" />
            Download HTML
          </button>
          <button
            type="button"
            onClick={onMarkdownDownload}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium text-fg-secondary transition-colors duration-1 ease-aw hover:border-accent hover:text-accent"
          >
            <FileText size={14} aria-hidden="true" />
            Download Markdown
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close export preview"
            className="rounded-md p-1.5 text-fg-muted hover:bg-surface-alt hover:text-fg"
          >
            <X size={16} />
          </button>
        </div>
      </header>
      <div className="flex-1 overflow-auto px-6 py-8">
        <div className="flex justify-center">{children}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// A4 sheet — uses inline styles throughout so the HTML download is
// self-contained. Tailwind isn't available in the downloaded file.
// ---------------------------------------------------------------------------

interface BriefExportSheetProps {
  product: ProductDetail;
  brief: BriefView;
  extracted: ExtractedClaims;
  mentions: Map<string, MentionView>;
}

const SHEET_STYLES: Record<string, React.CSSProperties> = {
  sheet: {
    width: "210mm",
    minHeight: "297mm",
    maxHeight: "297mm",
    padding: "14mm 16mm",
    background: "#FFFFFF",
    color: "#17171C",
    fontFamily: "Arial, Helvetica, sans-serif",
    boxShadow: "0 1px 2px rgba(23,23,28,0.06), 0 1px 3px rgba(23,23,28,0.04)",
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: "5mm",
    overflow: "hidden",
    pageBreakInside: "avoid",
  },
  topBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    fontSize: "9pt",
    color: "#6B6B73",
    letterSpacing: "0.05em",
    textTransform: "uppercase",
    fontWeight: 600,
    borderBottom: "1px solid #D9DCE7",
    paddingBottom: "2.5mm",
  },
  productHeader: {
    display: "flex",
    flexDirection: "column",
    gap: "1mm",
  },
  productName: {
    fontSize: "20pt",
    fontWeight: 600,
    color: "#17171C",
    lineHeight: 1.15,
    margin: 0,
  },
  productSub: {
    fontSize: "10pt",
    color: "#6B6B73",
  },
  statTilesRow: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: "3mm",
  },
  statTile: {
    border: "1px solid #D9DCE7",
    borderRadius: "4px",
    padding: "3mm 4mm",
    display: "flex",
    flexDirection: "column",
    gap: "1mm",
    background: "#FFFFFF",
  },
  statValue: {
    fontSize: "18pt",
    fontWeight: 600,
    color: "#17171C",
    fontVariantNumeric: "tabular-nums",
    lineHeight: 1,
  },
  statLabel: {
    fontSize: "8pt",
    color: "#6B6B73",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    fontWeight: 600,
  },
  sectionHeading: {
    fontSize: "9pt",
    color: "#444444",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    fontWeight: 700,
    paddingBottom: "1.5mm",
    borderBottom: "1px solid #D9DCE7",
    margin: 0,
  },
  aspectChipsRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: "1.5mm",
  },
  aspectChip: {
    fontSize: "8.5pt",
    fontWeight: 500,
    padding: "1mm 2.5mm",
    borderRadius: "10px",
    border: "1px solid",
    fontVariantNumeric: "tabular-nums",
  },
  summaryBlock: {
    borderLeft: "2px solid #5F00F8",
    background: "#F7F4FF",
    padding: "2.5mm 3.5mm",
    marginTop: "1mm",
  },
  summaryLabel: {
    fontSize: "7.5pt",
    color: "#5F00F8",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    fontWeight: 700,
    display: "block",
    marginBottom: "1mm",
  },
  summaryText: {
    fontSize: "10pt",
    fontStyle: "italic",
    color: "#17171C",
    lineHeight: 1.5,
    margin: 0,
  },
  claimList: {
    display: "flex",
    flexDirection: "column",
    gap: "2mm",
    margin: 0,
    padding: 0,
    listStyle: "none",
  },
  claimItem: {
    fontSize: "10pt",
    color: "#17171C",
    lineHeight: 1.4,
    display: "flex",
    gap: "2mm",
    alignItems: "baseline",
  },
  claimBullet: {
    color: "#5F00F8",
    fontWeight: 700,
    flexShrink: 0,
  },
  claimText: {
    flex: 1,
  },
  citeNumber: {
    fontSize: "8pt",
    fontWeight: 600,
    color: "#5F00F8",
    fontVariantNumeric: "tabular-nums",
    marginLeft: "1mm",
  },
  citationsList: {
    display: "flex",
    flexDirection: "column",
    gap: "0.8mm",
    margin: 0,
    padding: 0,
    listStyle: "none",
  },
  citationItem: {
    fontSize: "8.5pt",
    color: "#6B6B73",
    fontVariantNumeric: "tabular-nums",
  },
  citeKey: {
    color: "#5F00F8",
    fontWeight: 600,
    marginRight: "2mm",
  },
  footer: {
    marginTop: "auto",
    paddingTop: "3mm",
    borderTop: "1px solid #D9DCE7",
    fontSize: "8pt",
    color: "#6B6B73",
    display: "flex",
    justifyContent: "space-between",
  },
};

function chipColors(tone: "pos" | "neg" | "neutral" | "none"): React.CSSProperties {
  switch (tone) {
    case "pos":
      return { background: "#E8F4EC", borderColor: "#1F8A3F", color: "#1F8A3F" };
    case "neg":
      return { background: "#F8E5E5", borderColor: "#C13030", color: "#C13030" };
    case "neutral":
      return { background: "#FAF1DC", borderColor: "#B8860B", color: "#B8860B" };
    case "none":
    default:
      return { background: "#F4F5F7", borderColor: "#D9DCE7", color: "#6B6B73" };
  }
}

function countAspectTones(aspects: AspectRow[]): { pos: number; neg: number; net: number; tracked: number } {
  let pos = 0;
  let neg = 0;
  let sumNet = 0;
  let tracked = 0;
  for (const a of aspects) {
    if (a.total_mentions === 0) continue;
    tracked += 1;
    sumNet += a.net_sentiment;
    if (a.net_sentiment > 0.1) pos += 1;
    else if (a.net_sentiment < -0.1) neg += 1;
  }
  const net = tracked > 0 ? sumNet / tracked : 0;
  return { pos, neg, net, tracked };
}

const BriefExportSheet = forwardRef<HTMLDivElement, BriefExportSheetProps>(
  function BriefExportSheetInner(
    { product, brief, extracted, mentions },
    ref,
  ): JSX.Element {
    const { strengths, weaknesses, citedIds } = extracted;
    const stats = useMemo(() => countAspectTones(product.aspects), [product.aspects]);

    // Build a stable [n] → mention_id map across both claim sections so the
    // bracketed numbers in the body line up with the citations footer.
    const citeNumber = useMemo<Map<string, number>>(() => {
      const m = new Map<string, number>();
      let n = 1;
      for (const id of citedIds) {
        m.set(id, n);
        n += 1;
      }
      return m;
    }, [citedIds]);

    const aspectByName = useMemo(() => {
      const m = new Map<string, AspectRow>();
      for (const a of product.aspects) m.set(a.aspect, a);
      return m;
    }, [product.aspects]);

    const orderedAspects = Object.keys(ASPECT_LABELS);
    const sign = stats.net >= 0 ? "+" : "";

    return (
      <div ref={ref} className="a4-sheet print-target" style={SHEET_STYLES.sheet}>
        {/* Top bar — eyebrow + run id */}
        <div style={SHEET_STYLES.topBar}>
          <span>pulse-check · Standalone voice</span>
          <span>Run · {brief.run_id}</span>
        </div>

        {/* Product header */}
        <div style={SHEET_STYLES.productHeader}>
          <h1 style={SHEET_STYLES.productName}>{product.display_name}</h1>
          <span style={SHEET_STYLES.productSub}>
            {product.brand} · {formatNum(product.run_meta.total_mentions)} public mentions analyzed · {product.run_meta.window_label}
          </span>
        </div>

        {/* Stat tiles */}
        <div style={SHEET_STYLES.statTilesRow}>
          <div style={SHEET_STYLES.statTile}>
            <span style={SHEET_STYLES.statValue}>{formatNum(product.run_meta.total_mentions)}</span>
            <span style={SHEET_STYLES.statLabel}>Public mentions</span>
          </div>
          <div style={SHEET_STYLES.statTile}>
            <span style={{ ...SHEET_STYLES.statValue, color: "#1F8A3F" }}>{stats.pos}/{stats.tracked}</span>
            <span style={SHEET_STYLES.statLabel}>Positive aspects</span>
          </div>
          <div style={SHEET_STYLES.statTile}>
            <span style={{ ...SHEET_STYLES.statValue, color: "#C13030" }}>{stats.neg}/{stats.tracked}</span>
            <span style={SHEET_STYLES.statLabel}>Negative aspects</span>
          </div>
          <div style={SHEET_STYLES.statTile}>
            <span style={SHEET_STYLES.statValue}>{sign}{stats.net.toFixed(2)}</span>
            <span style={SHEET_STYLES.statLabel}>Avg net sentiment</span>
          </div>
        </div>

        {/* Aspect snapshot — 11 colored chips */}
        <div>
          <h2 style={SHEET_STYLES.sectionHeading}>Aspect snapshot</h2>
          <div style={{ ...SHEET_STYLES.aspectChipsRow, marginTop: "2mm" }}>
            {orderedAspects.map((aspect) => {
              const a = aspectByName.get(aspect);
              const tone: "pos" | "neg" | "neutral" | "none" =
                !a || a.total_mentions === 0 ? "none" : sentimentTone(a.net_sentiment);
              const value = !a || a.total_mentions === 0 ? "—" : `${a.net_sentiment >= 0 ? "+" : ""}${a.net_sentiment.toFixed(2)}`;
              return (
                <span
                  key={aspect}
                  style={{ ...SHEET_STYLES.aspectChip, ...chipColors(tone) }}
                >
                  {aspectLabel(aspect)} · {value}
                </span>
              );
            })}
          </div>
        </div>

        {/* Summary paragraph (a1_brief_v3+; rendered only when present) */}
        {brief.narrative.summary && (
          <div style={SHEET_STYLES.summaryBlock}>
            <span style={SHEET_STYLES.summaryLabel}>Summary</span>
            <p style={SHEET_STYLES.summaryText}>
              {brief.narrative.summary.text}
              {(() => {
                const nums = brief.narrative.summary.cited_mention_ids
                  .map((id) => citeNumber.get(id))
                  .filter((n): n is number => n !== undefined);
                if (nums.length === 0) return null;
                return (
                  <span style={SHEET_STYLES.citeNumber}>
                    [{nums.join(", ")}]
                  </span>
                );
              })()}
            </p>
          </div>
        )}

        {/* Strengths */}
        <div>
          <h2 style={SHEET_STYLES.sectionHeading}>Top strengths</h2>
          {strengths.length === 0 ? (
            <p style={{ ...SHEET_STYLES.claimItem, color: "#6B6B73" }}>No high-signal strengths in this brief.</p>
          ) : (
            <ul style={{ ...SHEET_STYLES.claimList, marginTop: "2mm" }}>
              {strengths.map((c, i) => (
                <ClaimLine key={i} claim={c} citeNumber={citeNumber} />
              ))}
            </ul>
          )}
        </div>

        {/* Weaknesses */}
        <div>
          <h2 style={SHEET_STYLES.sectionHeading}>Top complaints</h2>
          {weaknesses.length === 0 ? (
            <p style={{ ...SHEET_STYLES.claimItem, color: "#6B6B73" }}>No high-signal complaints in this brief.</p>
          ) : (
            <ul style={{ ...SHEET_STYLES.claimList, marginTop: "2mm" }}>
              {weaknesses.map((c, i) => (
                <ClaimLine key={i} claim={c} citeNumber={citeNumber} />
              ))}
            </ul>
          )}
        </div>

        {/* Citations */}
        {citedIds.length > 0 && (
          <div>
            <h2 style={SHEET_STYLES.sectionHeading}>Citations</h2>
            <ul style={{ ...SHEET_STYLES.citationsList, marginTop: "2mm" }}>
              {citedIds.map((id) => {
                const n = citeNumber.get(id) ?? 0;
                const m = mentions.get(id);
                const source = m ? shortSource(m.source_type, m.channel) : "—";
                const author = m?.author ? `@${m.author}` : "";
                const date = m?.published_at ? formatDate(m.published_at) : "";
                return (
                  <li key={id} style={SHEET_STYLES.citationItem}>
                    <span style={SHEET_STYLES.citeKey}>[{n}]</span>
                    {source}
                    {author ? ` · ${author}` : ""}
                    {date ? ` · ${date}` : ""}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Footer */}
        <div style={SHEET_STYLES.footer}>
          <span>Every claim cites a real mention. Verbatims live in the app.</span>
          <span>Generated by pulse-check · {formatDate(new Date().toISOString())}</span>
        </div>
      </div>
    );
  },
);

interface ClaimLineProps {
  claim: Claim;
  citeNumber: Map<string, number>;
}

function ClaimLine({ claim, citeNumber }: ClaimLineProps): JSX.Element {
  // Show the claim header (compact, scannable) — fall back to the first
  // sentence of the body if no header on the older a1_brief_v1 schema.
  const text = claim.header && claim.header.length > 0
    ? claim.header
    : (claim.claim_text.split(/\. /)[0] ?? claim.claim_text).slice(0, 110);
  const cites = claim.cited_mention_ids
    .map((id) => citeNumber.get(id))
    .filter((n): n is number => n !== undefined);
  return (
    <li style={SHEET_STYLES.claimItem}>
      <span style={SHEET_STYLES.claimBullet}>●</span>
      <span style={SHEET_STYLES.claimText}>
        {text}
        {cites.length > 0 && (
          <span style={SHEET_STYLES.citeNumber}>
            [{cites.join(", ")}]
          </span>
        )}
      </span>
    </li>
  );
}
