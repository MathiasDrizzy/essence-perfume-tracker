import Link from "next/link";
import { sql } from "@/lib/db";
import { formatCLP } from "@/lib/utils";
import DeleteAlertButton from "@/components/DeleteAlertButton";

export const dynamic = "force-dynamic";

type Row = {
  id: number;
  perfume_id: number;
  brand: string;
  name: string;
  volume_ml: number;
  concentration: string | null;
  target_price_clp: number;
  telegram_chat_id: string;
  active: boolean;
  triggered_at: string | null;
  current_min: number | null;
};

export default async function AlertsPage() {
  const rows = await sql<Row[]>`
    WITH latest AS (
      SELECT DISTINCT ON (l.id) l.perfume_id, ph.price_clp
      FROM listings l
      JOIN price_history ph ON ph.listing_id = l.id
      WHERE l.active AND ph.price_clp > 100
      ORDER BY l.id, ph.scraped_at DESC
    ),
    mins AS (
      SELECT perfume_id, MIN(price_clp) AS current_min
      FROM latest GROUP BY perfume_id
    )
    SELECT a.id, a.perfume_id, p.brand, p.name, p.volume_ml, p.concentration,
           a.target_price_clp, a.telegram_chat_id, a.active,
           a.triggered_at::text AS triggered_at,
           m.current_min::int AS current_min
    FROM alerts a
    JOIN perfumes p ON p.id = a.perfume_id
    LEFT JOIN mins m ON m.perfume_id = a.perfume_id
    ORDER BY a.active DESC, a.id DESC
  `;

  return (
    <div className="space-y-14">
      <section className="grid grid-cols-12 gap-6 lg:gap-10 items-end reveal reveal-1">
        <div className="col-span-12 lg:col-span-8">
          <p className="eyebrow mb-6">№ 002 · Vigilancia activa</p>
          <h1 className="font-display text-[clamp(48px,8vw,108px)] leading-[0.9] tracking-[-0.04em] font-light">
            Tus <em className="italic font-normal text-gold-deep">vigías</em> de precio.
          </h1>
          <p className="font-display text-xl md:text-2xl italic text-ink-soft mt-8 max-w-2xl leading-snug">
            Cuando una tienda baja al precio objetivo, Telegram suena. El catálogo entero está
            mirando por ti.
          </p>
        </div>
        <aside className="col-span-12 lg:col-span-4">
          <div className="border-t border-ink pt-4">
            <p className="eyebrow text-[10px]">Alertas registradas</p>
            <p className="font-display text-6xl tabular tracking-tight mt-2 leading-none">
              {rows.length}
            </p>
          </div>
        </aside>
      </section>

      <div className="hairline" />

      {rows.length === 0 ? (
        <section className="text-center py-32 reveal reveal-2">
          <p className="eyebrow mb-4">Bandeja vacía</p>
          <p className="font-display italic text-3xl md:text-4xl text-ink-soft max-w-xl mx-auto">
            Aún no estás vigilando ningún perfume.
            <br />
            <Link href="/" className="text-gold-deep no-italic">
              Explora el catálogo →
            </Link>
          </p>
        </section>
      ) : (
        <section className="reveal reveal-2">
          <table className="table-editorial">
            <thead>
              <tr>
                <th className="w-[40%]">Perfume vigilado</th>
                <th>Objetivo</th>
                <th>Mínimo actual</th>
                <th>Diferencia</th>
                <th>Estado</th>
                <th className="text-right">Acción</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const diff = r.current_min != null ? r.current_min - r.target_price_clp : null;
                const close = diff != null && diff > 0 && diff <= r.target_price_clp * 0.1;
                return (
                  <tr key={r.id}>
                    <td>
                      <p className="eyebrow text-[10px] text-gold-deep mb-1">{r.brand}</p>
                      <Link
                        href={`/perfume/${r.perfume_id}`}
                        className="font-display text-xl md:text-2xl leading-tight tracking-tight hover:text-gold-deep transition-colors"
                      >
                        {r.name}
                      </Link>
                      <p className="font-mono text-[11px] text-muted mt-1">
                        {r.volume_ml} ml {r.concentration ? `· ${r.concentration}` : ""}
                      </p>
                    </td>
                    <td>
                      <span className="font-display text-2xl tabular">
                        {formatCLP(r.target_price_clp)}
                      </span>
                    </td>
                    <td>
                      <span className="font-display text-2xl tabular">
                        {formatCLP(r.current_min)}
                      </span>
                    </td>
                    <td>
                      {diff == null ? (
                        <span className="font-mono text-muted text-xs">—</span>
                      ) : diff <= 0 ? (
                        <span className="font-mono text-olive text-sm">
                          ✓ {formatCLP(Math.abs(diff))} bajo objetivo
                        </span>
                      ) : (
                        <span
                          className={`font-mono text-sm ${close ? "text-burgundy" : "text-muted"}`}
                        >
                          +{formatCLP(diff)} sobre
                        </span>
                      )}
                    </td>
                    <td>
                      {r.triggered_at ? (
                        <span className="eyebrow text-olive">disparada</span>
                      ) : r.active ? (
                        <span className="eyebrow text-gold-deep shimmer">vigilando</span>
                      ) : (
                        <span className="eyebrow text-muted">inactiva</span>
                      )}
                    </td>
                    <td className="text-right">
                      <DeleteAlertButton id={r.id} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      <section className="border-t border-ink pt-10 grid grid-cols-1 md:grid-cols-3 gap-8 reveal reveal-3">
        <div>
          <p className="eyebrow">Paso 01</p>
          <h3 className="font-display text-2xl mt-2 leading-tight">Crea tu bot</h3>
          <p className="text-ink-soft text-sm mt-2 leading-relaxed">
            Escribe a <span className="font-mono text-ink">@BotFather</span> en Telegram. Pídele{" "}
            <span className="font-mono text-ink">/newbot</span>. Guarda el token recibido.
          </p>
        </div>
        <div>
          <p className="eyebrow">Paso 02</p>
          <h3 className="font-display text-2xl mt-2 leading-tight">Obtén tu chat ID</h3>
          <p className="text-ink-soft text-sm mt-2 leading-relaxed">
            Habla con tu nuevo bot. Envíale{" "}
            <span className="font-mono text-ink">/start</span> y te responderá con tu chat ID
            numérico.
          </p>
        </div>
        <div>
          <p className="eyebrow">Paso 03</p>
          <h3 className="font-display text-2xl mt-2 leading-tight">Vigila</h3>
          <p className="text-ink-soft text-sm mt-2 leading-relaxed">
            Entra a la ficha de cualquier perfume del catálogo, define el precio objetivo y pega
            tu chat ID. El catálogo hará el resto.
          </p>
        </div>
      </section>
    </div>
  );
}
