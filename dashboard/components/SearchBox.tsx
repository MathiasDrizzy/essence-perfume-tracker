"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type Suggestion =
  | { kind: "brand"; brand: string; count: number }
  | {
      kind: "perfume";
      id: number;
      brand: string;
      name: string;
      volume_ml: number;
      concentration: string | null;
    };

export default function SearchBox({ defaultValue = "" }: { defaultValue?: string }) {
  const [q, setQ] = useState(defaultValue);
  const [items, setItems] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Debounced fetch
  useEffect(() => {
    if (!q.trim() || q.trim().length < 2) {
      setItems([]);
      return;
    }
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/suggest?q=${encodeURIComponent(q.trim())}`);
        const data = await r.json();
        setItems(data.items || []);
        setHighlight(0);
      } finally {
        setLoading(false);
      }
    }, 180);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function commit(s: Suggestion) {
    if (s.kind === "perfume") {
      router.push(`/perfume/${s.id}`);
    } else {
      router.push(`/?brand=${encodeURIComponent(s.brand)}`);
    }
    setOpen(false);
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlight((h) => Math.min(h + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      if (open && items[highlight]) {
        e.preventDefault();
        commit(items[highlight]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative col-span-2">
      <span className="eyebrow text-[10px] block mb-2">
        Búsqueda
        {loading && <span className="ml-2 text-muted">·</span>}
      </span>
      <input
        type="text"
        name="q"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
        placeholder="Erba Pura, Armaf, Dior…"
        autoComplete="off"
        className="field font-display text-lg"
      />

      {open && items.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-full mt-1 z-50 bg-bone-soft border-2 border-ink shadow-[0_24px_60px_-12px_rgba(0,0,0,0.6)] max-h-96 overflow-auto divide-y divide-rule"
        >
          {items.map((s, i) => (
            <li
              key={s.kind === "perfume" ? `p-${s.id}` : `b-${s.brand}`}
              role="option"
              aria-selected={i === highlight}
              onMouseEnter={() => setHighlight(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(s);
              }}
              className={`px-4 py-3 cursor-pointer ${i === highlight ? "bg-rule/60" : ""}`}
            >
              {s.kind === "brand" ? (
                <div className="flex items-baseline justify-between gap-3">
                  <div>
                    <p className="eyebrow text-[9px] text-gold-deep mb-1">Casa</p>
                    <p className="font-display text-lg tracking-tight">{s.brand}</p>
                  </div>
                  <span className="font-mono text-[10px] text-muted tabular">
                    {s.count} perfumes
                  </span>
                </div>
              ) : (
                <div className="flex items-baseline justify-between gap-3">
                  <div>
                    <p className="eyebrow text-[9px] text-gold-deep mb-1">{s.brand}</p>
                    <p className="font-display text-lg tracking-tight leading-tight">{s.name}</p>
                  </div>
                  <span className="font-mono text-[10px] text-muted tabular whitespace-nowrap">
                    {s.volume_ml} ml {s.concentration ? `· ${s.concentration}` : ""}
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {open && !loading && q.trim().length >= 2 && items.length === 0 && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-bone-soft border-2 border-ink px-4 py-3">
          <p className="font-mono text-xs text-muted">sin coincidencias para "{q}"</p>
        </div>
      )}
    </div>
  );
}
