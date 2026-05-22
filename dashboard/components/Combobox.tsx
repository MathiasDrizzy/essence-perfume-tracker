"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export type ComboboxOption = { value: string; label: string; meta?: string };

/** Combobox accesible con filtro por substring y teclado (↑/↓/Enter/Esc).
 *  - Si el texto exactamente matchea una opción, se usa su `value`.
 *  - Si el campo queda vacío, se envía "" (sin filtro).
 *  - Si el texto es libre y no matchea, se envía igualmente como `value`
 *    (útil para búsqueda libre). */
export default function Combobox({
  name,
  label,
  options,
  defaultValue = "",
  placeholder,
  className,
}: {
  name: string;
  label?: string;
  options: ComboboxOption[];
  defaultValue?: string;
  placeholder?: string;
  className?: string;
}) {
  // Determina label inicial a partir del defaultValue.
  // Si defaultValue es vacío, dejamos el input vacío (no mostramos la etiqueta
  // del "sin filtro") para que se vea el placeholder.
  const initialLabel = useMemo(() => {
    if (!defaultValue) return "";
    const match = options.find((o) => o.value === defaultValue);
    return match ? match.label : defaultValue;
  }, [defaultValue, options]);

  const [query, setQuery] = useState(initialLabel);
  const [selectedValue, setSelectedValue] = useState(defaultValue);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const trimmed = query.trim();
    if (!trimmed) return options;
    const q = trimmed.toLowerCase();
    const starts: ComboboxOption[] = [];
    const includes: ComboboxOption[] = [];
    for (const o of options) {
      const l = o.label.toLowerCase();
      if (l.startsWith(q)) starts.push(o);
      else if (l.includes(q)) includes.push(o);
    }
    return [...starts, ...includes];
  }, [query, options]);

  useEffect(() => {
    setHighlight(0);
  }, [filtered.length]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
        // Si lo que se tipeó no matchea exactamente, asumir valor vacío
        const exact = options.find((o) => o.label.toLowerCase() === query.trim().toLowerCase());
        if (exact) setSelectedValue(exact.value);
        else if (!query.trim()) setSelectedValue("");
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [query, options]);

  function pick(option: ComboboxOption) {
    setQuery(option.label);
    setSelectedValue(option.value);
    setOpen(false);
    inputRef.current?.blur();
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlight((h) => Math.min(h + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      if (open && filtered[highlight]) {
        e.preventDefault();
        pick(filtered[highlight]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className={`relative ${className || ""}`}>
      {label && <span className="eyebrow text-[10px] block mb-2">{label}</span>}
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          if (e.target.value === "") setSelectedValue("");
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
        placeholder={placeholder}
        autoComplete="off"
        className="field"
      />
      <input type="hidden" name={name} value={selectedValue} />

      {open && filtered.length > 0 && (
        <div
          role="listbox"
          className="absolute left-0 right-0 top-full mt-1 z-50 bg-bone-soft border-2 border-ink shadow-[0_24px_60px_-12px_rgba(0,0,0,0.6)] max-h-[420px] overflow-auto"
        >
          <ul>
            {filtered.map((o, i) => (
              <li
                key={o.value || "__empty"}
                role="option"
                aria-selected={i === highlight}
                onMouseEnter={() => setHighlight(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(o);
                }}
                className={`px-3 py-2 cursor-pointer flex items-baseline justify-between gap-3 ${
                  i === highlight ? "bg-rule/50" : ""
                }`}
              >
                <span
                  className={`font-display text-base tracking-tight ${
                    !o.value ? "italic text-muted" : ""
                  }`}
                >
                  {o.label}
                </span>
                {o.meta && (
                  <span className="font-mono text-[10px] text-muted tabular">{o.meta}</span>
                )}
              </li>
            ))}
          </ul>
          <div className="sticky bottom-0 left-0 right-0 px-3 py-2 bg-bone-soft border-t border-rule">
            <p className="font-mono text-[10px] text-muted tabular">
              {filtered.length.toLocaleString("es-CL")} marcas · sigue escribiendo para filtrar
            </p>
          </div>
        </div>
      )}

      {open && filtered.length === 0 && query && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-bone-soft border-2 border-ink px-3 py-3">
          <p className="font-mono text-xs text-muted">sin coincidencias</p>
        </div>
      )}
    </div>
  );
}
