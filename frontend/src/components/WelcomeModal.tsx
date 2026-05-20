import { useEffect } from "react";
import { AlertCircle, Sparkles, Users, X } from "lucide-react";

interface WelcomeModalProps {
  open: boolean;
  onClose: () => void;
}

export function WelcomeModal({ open, onClose }: WelcomeModalProps): JSX.Element | null {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="welcome-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-fg/40 p-6 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-3xl rounded-lg border border-border bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-border px-8 pb-4 pt-6">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
              pulse-check
            </span>
            <h2 id="welcome-title" className="mt-1 text-xl font-semibold text-fg">
              At a glance
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close welcome"
            className="rounded-md p-1.5 text-fg-muted hover:bg-surface-alt hover:text-fg"
          >
            <X size={16} />
          </button>
        </div>

        <div className="grid grid-cols-3 gap-6 px-8 py-6">
          <Section
            icon={<AlertCircle size={18} className="text-accent" aria-hidden="true" />}
            eyebrow="The problem"
            body="Owner voice is scattered across reddit, news, and video — invisible at the scale of a stakeholder review."
            diagram={<ProblemSvg />}
          />
          <Section
            icon={<Sparkles size={18} className="text-accent" aria-hidden="true" />}
            eyebrow="What this does"
            body="Surfaces what owners actually say — by aspect, by SKU, with every claim cited to a real mention."
            diagram={<FunnelSvg />}
          />
          <Section
            icon={<Users size={18} className="text-accent" aria-hidden="true" />}
            eyebrow="Who uses it"
            body="Across product, marketing, engineering, and sales. Quarterly cadence."
            diagram={<PersonaSvg />}
          />
        </div>

        <div className="border-t border-border bg-surface-alt/40 px-8 py-5">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
            How each function uses it
          </span>
          <div className="mt-3 flex flex-col gap-2">
            <UseCaseRow
              label="PM"
              body="Spot emerging quality issues per SKU before they escalate."
            />
            <UseCaseRow
              label="Mkt"
              body="Pull genuine talking points + complaints to lead on."
            />
            <UseCaseRow
              label="Eng"
              body="Surface thermal / battery / QA patterns across the model lineup."
            />
            <UseCaseRow
              label="Sales"
              body="Head-to-head leverage on the 11 tracked aspects in competitive deals."
            />
          </div>
        </div>

        <div className="flex justify-end border-t border-border px-8 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}

interface SectionProps {
  icon: JSX.Element;
  eyebrow: string;
  body: string;
  diagram: JSX.Element;
}

function Section({ icon, eyebrow, body, diagram }: SectionProps): JSX.Element {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
          {eyebrow}
        </span>
      </div>
      <p className="text-sm leading-relaxed text-fg-secondary">{body}</p>
      <div className="mt-2 flex justify-center">{diagram}</div>
    </div>
  );
}

interface UseCaseRowProps {
  label: string;
  body: string;
}

function UseCaseRow({ label, body }: UseCaseRowProps): JSX.Element {
  return (
    <div className="flex items-center gap-3">
      <span className="inline-flex h-6 min-w-[48px] items-center justify-center rounded-full bg-accent px-2 text-[10px] font-bold uppercase tracking-wide text-white">
        {label}
      </span>
      <span className="text-sm text-fg-secondary">{body}</span>
    </div>
  );
}

function ProblemSvg(): JSX.Element {
  return (
    <svg viewBox="0 0 200 80" className="h-20 w-full text-fg-muted" aria-hidden="true">
      <rect x="6" y="10" width="44" height="18" rx="3" fill="currentColor" opacity="0.18" />
      <text x="28" y="22" fontSize="9" textAnchor="middle" fill="currentColor">
        reddit
      </text>

      <rect x="58" y="38" width="44" height="18" rx="3" fill="currentColor" opacity="0.18" />
      <text x="80" y="50" fontSize="9" textAnchor="middle" fill="currentColor">
        news
      </text>

      <rect x="14" y="56" width="44" height="18" rx="3" fill="currentColor" opacity="0.18" />
      <text x="36" y="68" fontSize="9" textAnchor="middle" fill="currentColor">
        video
      </text>

      <path
        d="M 105 45 L 140 45"
        stroke="currentColor"
        strokeWidth="1"
        strokeDasharray="3,2"
        opacity="0.5"
      />
      <path
        d="M 138 41 L 145 45 L 138 49"
        stroke="currentColor"
        strokeWidth="1"
        fill="none"
        opacity="0.5"
      />

      <text
        x="170"
        y="58"
        fontSize="28"
        textAnchor="middle"
        fontWeight="bold"
        fill="currentColor"
        opacity="0.25"
      >
        ?
      </text>
    </svg>
  );
}

function FunnelSvg(): JSX.Element {
  return (
    <svg viewBox="0 0 200 80" className="h-20 w-full text-fg-muted" aria-hidden="true">
      <rect x="10" y="6" width="180" height="14" rx="2" fill="currentColor" opacity="0.18" />
      <text x="100" y="16" fontSize="9" textAnchor="middle" fill="currentColor">
        5,061 mentions
      </text>

      <path d="M 100 22 L 100 28" stroke="currentColor" strokeWidth="1" opacity="0.6" />

      {Array.from({ length: 11 }).map((_, i) => (
        <rect
          key={i}
          x={48 + i * 9.5}
          y="30"
          width="6"
          height="16"
          rx="1"
          fill="#5F00F8"
          opacity="0.55"
        />
      ))}

      <path d="M 100 48 L 100 54" stroke="currentColor" strokeWidth="1" opacity="0.6" />

      <rect x="78" y="56" width="44" height="16" rx="2" fill="#5F00F8" opacity="0.85" />
      <text x="100" y="67" fontSize="8" textAnchor="middle" fill="white" fontWeight="bold">
        brief
      </text>
    </svg>
  );
}

function PersonaSvg(): JSX.Element {
  return (
    <svg viewBox="0 0 200 80" className="h-20 w-full text-fg-muted" aria-hidden="true">
      <line
        x1="20"
        y1="32"
        x2="180"
        y2="32"
        stroke="currentColor"
        strokeWidth="1"
        opacity="0.35"
      />

      <circle cx="30" cy="32" r="11" fill="#5F00F8" opacity="0.85" />
      <text x="30" y="35" fontSize="7" textAnchor="middle" fill="white" fontWeight="bold">
        PM
      </text>

      <circle cx="80" cy="32" r="11" fill="#5F00F8" opacity="0.85" />
      <text x="80" y="35" fontSize="7" textAnchor="middle" fill="white" fontWeight="bold">
        Mkt
      </text>

      <circle cx="130" cy="32" r="11" fill="#5F00F8" opacity="0.85" />
      <text x="130" y="35" fontSize="7" textAnchor="middle" fill="white" fontWeight="bold">
        Eng
      </text>

      <circle cx="170" cy="32" r="11" fill="#5F00F8" opacity="0.85" />
      <text x="170" y="35" fontSize="6" textAnchor="middle" fill="white" fontWeight="bold">
        Sales
      </text>

      <text
        x="100"
        y="60"
        fontSize="9"
        textAnchor="middle"
        fill="currentColor"
        opacity="0.7"
      >
        quarterly cadence
      </text>
    </svg>
  );
}
