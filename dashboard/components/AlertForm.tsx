"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { formatCLP } from "@/lib/utils";

export default function AlertForm({
  perfumeId,
  minNow,
}: {
  perfumeId: number;
  minNow: number | null;
}) {
  const [targetPrice, setTargetPrice] = useState("");
  const [chatId, setChatId] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    startTransition(async () => {
      const res = await fetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          perfume_id: perfumeId,
          target_price_clp: Number(targetPrice.replace(/[^\d]/g, "")),
          telegram_chat_id: chatId.trim(),
        }),
      });
      if (res.ok) {
        setMsg({ ok: true, text: "Alerta registrada. Tu Telegram suena cuando alguna tienda baje." });
        setTargetPrice("");
        router.refresh();
      } else {
        const body = await res.json().catch(() => ({ error: "unknown" }));
        setMsg({ ok: false, text: `No se pudo guardar: ${body.error ?? res.statusText}` });
      }
    });
  }

  return (
    <form onSubmit={submit} className="space-y-6 bg-bone-soft/40 p-6 border border-rule">
      <div className="grid grid-cols-2 gap-6">
        <label className="block">
          <span className="eyebrow text-[10px] block mb-2">Precio objetivo (CLP)</span>
          <input
            type="text"
            inputMode="numeric"
            value={targetPrice}
            onChange={(e) => setTargetPrice(e.target.value)}
            placeholder="25.000"
            required
            className="field font-display text-2xl tabular"
          />
          {minNow != null && (
            <p className="font-mono text-[10px] text-muted mt-2">
              · mín. actual {formatCLP(minNow)}
            </p>
          )}
        </label>
        <label className="block">
          <span className="eyebrow text-[10px] block mb-2">Chat ID Telegram</span>
          <input
            type="text"
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            placeholder="123456789"
            required
            className="field font-mono text-base"
          />
          <p className="font-mono text-[10px] text-muted mt-2">
            · envía /start al bot para obtenerlo
          </p>
        </label>
      </div>

      <div className="flex items-center justify-between gap-4 border-t border-rule pt-4">
        <p className="font-display italic text-sm text-ink-soft max-w-xs">
          El bot te escribe en cuanto alguna de las {10} tiendas marque tu precio o menos.
        </p>
        <button type="submit" disabled={pending} className="btn-gold">
          {pending ? "Guardando…" : "Vigilar"}
        </button>
      </div>

      {msg && (
        <p
          className={`font-mono text-xs ${
            msg.ok ? "text-olive" : "text-burgundy"
          } border-t border-rule pt-3`}
        >
          {msg.text}
        </p>
      )}
    </form>
  );
}
