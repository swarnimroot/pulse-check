import { forwardRef, useEffect, useMemo, useRef, useState } from "react";
import { X, Download, FileText, Printer } from "lucide-react";
import { api } from "@/lib/api";
import {
  PAIR_LEAD_THRESHOLD,
  buildPairCitedIds,
  computePairLeaders,
  pairBriefToMarkdown,
  type PairExportLeaders,
  type PairLeaderBullet,
} from "@/lib/pairExportMarkdown";
import type {
  BriefView,
  MentionView,
  PairAspectRow,
  PairBriefNarrative,
  PairResponse,
} from "@/lib/types";

/**
 * PairBriefExportButton — comparative-brief mirror of `BriefExportButton`.
 *
 * Same 3-route export surface (Save as PDF · Download HTML · Download
 * Markdown), same A4 preview, but the sheet layout reflects the pair brief
 * shape: head-to-head stat tiles, two per-product aspect chip rows, an
 * accent contrast block, and "Where X leads" / "Where Y leads" bullets
 * derived from PairResponse aspect deltas (threshold 0.10 — same rule as
 * the in-app scorecard's leader highlight).
 *
 * The overlay (toolbar + scrim + scrollable preview) is duplicated rather
 * than extracted from `BriefExportButton.tsx` to keep the standalone export
 * untouched. If a third export surface lands later, that's the right moment
 * to extract.
 */

interface PairBriefExportButtonProps {
  pair: PairResponse;
  brief: BriefView;
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

function sentimentTone(net: number): "pos" | "neg" | "neutral" {
  if (net > 0.1) return "pos";
  if (net < -0.1) return "neg";
  return "neutral";
}

export function PairBriefExportButton({
  pair,
  brief,
}: PairBriefExportButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [mentions, setMentions] = useState<Map<string, MentionView>>(new Map());

  const leaders = useMemo<PairExportLeaders>(() => computePairLeaders(pair), [pair]);

  const narrative = brief.narrative as unknown as PairBriefNarrative;
  const contrastIds = narrative.contrast?.cited_mention_ids ?? [];

  const citedIds = useMemo<string[]>(
    () => buildPairCitedIds(contrastIds, leaders),
    [contrastIds, leaders],
  );

  const citeNumber = useMemo<Map<string, number>>(() => {
    const m = new Map<string, number>();
    citedIds.forEach((id, i) => m.set(id, i + 1));
    return m;
  }, [citedIds]);

  // Lazy-fetch cited mentions when the overlay opens — never preloaded since
  // most viewers never click Export. Keyed by mention_id so each [n] entry in
  // the citations footer can resolve its source row.
  useEffect(() => {
    if (!open) return;
    if (citedIds.length === 0) return;
    let cancelled = false;
    api
      .mentions(citedIds)
      .then((res) => {
        if (cancelled) return;
        const m = new Map<string, MentionView>();
        for (const x of res.mentions) m.set(x.mention_id, x);
        setMentions(m);
      })
      .catch(() => {
        // Citations footer renders without source detail in this case; the
        // [n] numbers stay correct so the export still parses.
      });
    return () => {
      cancelled = true;
    };
  }, [open, citedIds]);

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

  const filenameStem = `pulse-check-pair-${pair.primary.product_id}-vs-${pair.competitor.product_id}-${new Date().toISOString().slice(0, 10)}`;

  const handlePrint = (): void => {
    document.body.classList.add("printing");
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
  <title>pulse-check — ${pair.primary.display_name} vs ${pair.competitor.display_name}</title>
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
    a.download = `${filenameStem}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleMarkdownDownload = (): void => {
    const md = pairBriefToMarkdown({ pair, brief, mentions });
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filenameStem}.md`;
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
        Export comparison
      </button>
      {open && (
        <PairExportOverlay
          onClose={() => setOpen(false)}
          onPrint={handlePrint}
          onHtmlDownload={handleHtmlDownload}
          onMarkdownDownload={handleMarkdownDownload}
        >
          <PairBriefExportSheet
            ref={sheetRef}
            pair={pair}
            brief={brief}
            leaders={leaders}
            citedIds={citedIds}
            citeNumber={citeNumber}
            mentions={mentions}
          />
        </PairExportOverlay>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Overlay — full-screen scrim + toolbar + scrollable A4 preview.
// Duplicated from BriefExportButton (per file header rationale).
// ---------------------------------------------------------------------------

interface PairExportOverlayProps {
  onClose: () => void;
  onPrint: () => void;
  onHtmlDownload: () => void;
  onMarkdownDownload: () => void;
  children: React.ReactNode;
}

function PairExportOverlay({
  onClose,
  onPrint,
  onHtmlDownload,
  onMarkdownDownload,
  children,
}: PairExportOverlayProps): JSX.Element {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Pair brief export preview"
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
// A4 sheet — inline styles throughout so the HTML download is self-contained.
// ---------------------------------------------------------------------------

interface PairBriefExportSheetProps {
  pair: PairResponse;
  brief: BriefView;
  leaders: PairExportLeaders;
  citedIds: string[];
  citeNumber: Map<string, number>;
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
    gap: "4mm",
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
    fontSize: "18pt",
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
    gridTemplateColumns: "repeat(3, 1fr)",
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
    textAlign: "center" as const,
    alignItems: "center" as const,
  },
  statValue: {
    fontSize: "16pt",
    fontWeight: 600,
    color: "#5F00F8",
    fontVariantNumeric: "tabular-nums",
    lineHeight: 1,
  },
  statValueNeutral: {
    fontSize: "16pt",
    fontWeight: 600,
    color: "#6B6B73",
    fontVariantNumeric: "tabular-nums",
    lineHeight: 1,
  },
  statHeadline: {
    fontSize: "9pt",
    color: "#17171C",
    fontWeight: 600,
    textAlign: "center" as const,
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
  aspectRowLabel: {
    fontSize: "9pt",
    color: "#17171C",
    fontWeight: 600,
    marginBottom: "1.5mm",
    marginTop: "2mm",
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
  contrastBlock: {
    borderLeft: "2px solid #5F00F8",
    background: "#F7F4FF",
    padding: "2.5mm 3.5mm",
    marginTop: "1mm",
  },
  contrastLabel: {
    fontSize: "7.5pt",
    color: "#5F00F8",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    fontWeight: 700,
    display: "block",
    marginBottom: "1mm",
  },
  contrastText: {
    fontSize: "10pt",
    fontStyle: "italic",
    color: "#17171C",
    lineHeight: 1.5,
    margin: 0,
  },
  leaderList: {
    display: "flex",
    flexDirection: "column",
    gap: "1.5mm",
    margin: 0,
    padding: 0,
    listStyle: "none",
  },
  leaderItem: {
    fontSize: "9.5pt",
    color: "#17171C",
    lineHeight: 1.4,
    display: "flex",
    gap: "2mm",
    alignItems: "baseline",
  },
  leaderBullet: {
    color: "#5F00F8",
    fontWeight: 700,
    flexShrink: 0,
  },
  leaderText: {
    flex: 1,
  },
  leaderAspect: {
    fontWeight: 700,
  },
  leaderMetric: {
    color: "#444444",
    fontVariantNumeric: "tabular-nums",
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

function aspectChipForCell(
  row: PairAspectRow,
  side: "primary" | "competitor",
): JSX.Element {
  const cell = side === "primary" ? row.primary : row.competitor;
  const tone: "pos" | "neg" | "neutral" | "none" =
    !cell || cell.total_mentions === 0
      ? "none"
      : sentimentTone(cell.net_sentiment);
  const value = !cell || cell.total_mentions === 0
    ? "—"
    : `${cell.net_sentiment >= 0 ? "+" : ""}${cell.net_sentiment.toFixed(2)}`;
  return (
    <span
      key={`${row.aspect}-${side}`}
      style={{ ...SHEET_STYLES.aspectChip, ...chipColors(tone) }}
    >
      {aspectLabel(row.aspect)} · {value}
    </span>
  );
}

const PairBriefExportSheet = forwardRef<HTMLDivElement, PairBriefExportSheetProps>(
  function PairBriefExportSheetInner(
    { pair, brief, leaders, citedIds, citeNumber, mentions },
    ref,
  ): JSX.Element {
    const narrative = brief.narrative as unknown as PairBriefNarrative;
    const contrast = narrative.contrast;
    const total = pair.rows.length;

    return (
      <div ref={ref} className="a4-sheet print-target" style={SHEET_STYLES.sheet}>
        {/* Top bar */}
        <div style={SHEET_STYLES.topBar}>
          <span>pulse-check · Comparative voice</span>
          <span>Run · {pair.run_id ?? brief.run_id}</span>
        </div>

        {/* Header */}
        <div style={SHEET_STYLES.productHeader}>
          <h1 style={SHEET_STYLES.productName}>
            {pair.primary.display_name} <span style={{ color: "#6B6B73", fontWeight: 400 }}>vs</span> {pair.competitor.display_name}
          </h1>
          <span style={SHEET_STYLES.productSub}>
            {pair.primary.brand} vs {pair.competitor.brand} · head-to-head on {total} aspects · generated {formatDate(pair.generated_at)}
          </span>
        </div>

        {/* Stat tiles */}
        <div style={SHEET_STYLES.statTilesRow}>
          <div style={SHEET_STYLES.statTile}>
            <span style={SHEET_STYLES.statValue}>
              {pair.primary_leads_count} / {total}
            </span>
            <span style={SHEET_STYLES.statHeadline}>
              {pair.primary.display_name}
            </span>
            <span style={SHEET_STYLES.statLabel}>Leads</span>
          </div>
          <div style={SHEET_STYLES.statTile}>
            <span style={SHEET_STYLES.statValueNeutral}>
              {pair.ties_count} / {total}
            </span>
            <span style={SHEET_STYLES.statHeadline}>Ties</span>
            <span style={SHEET_STYLES.statLabel}>
              within ±{PAIR_LEAD_THRESHOLD.toFixed(2)}
            </span>
          </div>
          <div style={SHEET_STYLES.statTile}>
            <span style={SHEET_STYLES.statValue}>
              {pair.competitor_leads_count} / {total}
            </span>
            <span style={SHEET_STYLES.statHeadline}>
              {pair.competitor.display_name}
            </span>
            <span style={SHEET_STYLES.statLabel}>Leads</span>
          </div>
        </div>

        {/* Aspect comparison — two parallel chip rows */}
        <div>
          <h2 style={SHEET_STYLES.sectionHeading}>Aspect comparison</h2>
          <div style={SHEET_STYLES.aspectRowLabel}>{pair.primary.display_name}</div>
          <div style={SHEET_STYLES.aspectChipsRow}>
            {pair.rows.map((row) => aspectChipForCell(row, "primary"))}
          </div>
          <div style={SHEET_STYLES.aspectRowLabel}>{pair.competitor.display_name}</div>
          <div style={SHEET_STYLES.aspectChipsRow}>
            {pair.rows.map((row) => aspectChipForCell(row, "competitor"))}
          </div>
        </div>

        {/* Contrast paragraph */}
        {contrast && contrast.text.length > 0 && (
          <div style={SHEET_STYLES.contrastBlock}>
            <span style={SHEET_STYLES.contrastLabel}>Contrast</span>
            <p style={SHEET_STYLES.contrastText}>
              {contrast.text}
              {(() => {
                const nums = contrast.cited_mention_ids
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

        {/* Where primary leads */}
        <div>
          <h2 style={SHEET_STYLES.sectionHeading}>
            Where {pair.primary.display_name} leads
          </h2>
          {leaders.primary.length === 0 ? (
            <p style={{ ...SHEET_STYLES.leaderItem, color: "#6B6B73", marginTop: "2mm" }}>
              No aspects above ±{PAIR_LEAD_THRESHOLD.toFixed(2)} threshold.
            </p>
          ) : (
            <ul style={{ ...SHEET_STYLES.leaderList, marginTop: "2mm" }}>
              {leaders.primary.map((bullet, i) => (
                <LeaderLine key={i} bullet={bullet} citeNumber={citeNumber} />
              ))}
            </ul>
          )}
        </div>

        {/* Where competitor leads */}
        <div>
          <h2 style={SHEET_STYLES.sectionHeading}>
            Where {pair.competitor.display_name} leads
          </h2>
          {leaders.competitor.length === 0 ? (
            <p style={{ ...SHEET_STYLES.leaderItem, color: "#6B6B73", marginTop: "2mm" }}>
              No aspects above ±{PAIR_LEAD_THRESHOLD.toFixed(2)} threshold.
            </p>
          ) : (
            <ul style={{ ...SHEET_STYLES.leaderList, marginTop: "2mm" }}>
              {leaders.competitor.map((bullet, i) => (
                <LeaderLine key={i} bullet={bullet} citeNumber={citeNumber} />
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

interface LeaderLineProps {
  bullet: PairLeaderBullet;
  citeNumber: Map<string, number>;
}

function LeaderLine({ bullet, citeNumber }: LeaderLineProps): JSX.Element {
  const { row } = bullet;
  const priNet = row.primary
    ? `${row.primary.net_sentiment >= 0 ? "+" : ""}${row.primary.net_sentiment.toFixed(2)}`
    : "—";
  const compNet = row.competitor
    ? `${row.competitor.net_sentiment >= 0 ? "+" : ""}${row.competitor.net_sentiment.toFixed(2)}`
    : "—";
  const delta = `+${Math.abs(row.delta).toFixed(2)}`;
  const nums = bullet.citedMentionIds
    .map((id) => citeNumber.get(id))
    .filter((n): n is number => n !== undefined);
  return (
    <li style={SHEET_STYLES.leaderItem}>
      <span style={SHEET_STYLES.leaderBullet}>●</span>
      <span style={SHEET_STYLES.leaderText}>
        <span style={SHEET_STYLES.leaderAspect}>{aspectLabel(row.aspect)}</span>
        <span style={SHEET_STYLES.leaderMetric}>
          {" "}— net {priNet} vs {compNet} (Δ {delta})
        </span>
        {nums.length > 0 && (
          <span style={SHEET_STYLES.citeNumber}>
            [{nums.join(", ")}]
          </span>
        )}
      </span>
    </li>
  );
}
