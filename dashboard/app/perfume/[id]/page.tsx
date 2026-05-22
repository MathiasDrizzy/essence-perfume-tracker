import Link from "next/link";
import { notFound } from "next/navigation";
import { sql } from "@/lib/db";
import { formatCLP, retailerLabel, retailerColor } from "@/lib/utils";
import PriceChart from "@/components/PriceChart";
import AlertForm from "@/components/AlertForm";

export const dynamic = "force-dynamic";

type Perfume = {
  id: number;
  brand: string;
  name: string;
  concentration: string | null;
  volume_ml: number;
  gender: string | null;
};

type Latest = {
  retailer: string;
  url: string;
  price_clp: number;
  list_price_clp: number | null;
  scraped_at: string;
};

type HistRow = { retailer: string; scraped_at: string; price_clp: number };

async function getData(id: number) {
  const [perfume] = await sql<Perfume[]>`SELECT * FROM perfumes WHERE id = ${id}`;
  if (!perfume) return null;

  const latest = await sql<Latest[]>`
    SELECT DISTINCT ON (l.retailer)
      l.retailer, l.url, ph.price_clp, ph.list_price_clp, ph.scraped_at::text AS scraped_at
    FROM listings l
    JOIN price_history ph ON ph.listing_id = l.id
    WHERE l.perfume_id = ${id} AND l.active AND ph.price_clp > 100
    ORDER BY l.retailer, ph.scraped_at DESC
  `;

  const history = await sql<HistRow[]>`
    SELECT l.retailer, ph.scraped_at::text AS scraped_at, MIN(ph.price_clp) AS price_clp
    FROM listings l
    JOIN price_history ph ON ph.listing_id = l.id
    WHERE l.perfume_id = ${id} AND l.active AND ph.scraped_at > NOW() - INTERVAL '180 days'
    GROUP BY l.retailer, ph.scraped_at
    ORDER BY ph.scraped_at ASC
  `;

  return { perfume, latest, history };
}

export default async function PerfumeDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const data = await getData(Number(id));
  if (!data) return notFound();
  const { perfume, latest, history } = data;
  const sorted = latest.slice().sort((a, b) => a.price_clp - b.price_clp);
  const min = sorted[0]?.price_clp ?? null;
  const max = sorted.at(-1)?.price_clp ?? null;
  const spread = min && max && max > min ? Math.round((1 - min / max) * 100) : 0;
  const savings = min && max ? max - min : 0;

  return (
    <div className="space-y-16">
      <Link
        href="/"
        className="inline-flex items-center gap-2 eyebrow link-editorial reveal reveal-1"
      >
        ← volver al catálogo
      </Link>

      {/* HERO DE PRODUCTO */}
      <section className="grid grid-cols-12 gap-6 lg:gap-12 items-start reveal reveal-2">
        <div className="col-span-12 lg:col-span-8">
          <p className="eyebrow text-gold-deep mb-4">
            ficha №{String(perfume.id).padStart(5, "0")} ·{" "}
            <span className="text-muted">{perfume.brand}</span>
          </p>
          <h1 className="font-display text-[clamp(40px,7vw,96px)] leading-[0.92] tracking-[-0.035em] font-light">
            {perfume.name}
          </h1>
          <div className="flex flex-wrap items-baseline gap-6 mt-8 text-ink-soft">
            <Spec label="Casa" value={perfume.brand} />
            <Spec label="Formato" value={`${perfume.volume_ml} ml`} />
            {perfume.concentration && (
              <Spec label="Concentración" value={perfume.concentration} />
            )}
            {perfume.gender && <Spec label="Destinado a" value={perfume.gender} />}
          </div>
        </div>

        {/* TARJETA DE PRECIO HERO */}
        <aside className="col-span-12 lg:col-span-4">
          <div className="border-t border-ink pt-5 space-y-6 bg-bone-soft/60 p-6">
            <div>
              <p className="eyebrow mb-2">Mejor precio hoy</p>
              <p className="font-display text-5xl tabular leading-none">{formatCLP(min)}</p>
              {sorted[0] && (
                <p className="mt-3">
                  <span
                    className="chip-retailer"
                    style={
                      {
                        ["--chip-color" as string]: retailerColor(sorted[0].retailer),
                      } as React.CSSProperties
                    }
                  >
                    {retailerLabel(sorted[0].retailer)}
                  </span>
                </p>
              )}
            </div>

            {savings > 0 && (
              <div className="border-t border-rule pt-4">
                <p className="eyebrow mb-1">Ahorro vs. más caro</p>
                <p className="font-display text-2xl text-burgundy tabular leading-none">
                  −{formatCLP(savings)}{" "}
                  <span className="text-base text-muted ml-1">({spread}%)</span>
                </p>
              </div>
            )}

            <div className="border-t border-rule pt-4 flex items-baseline justify-between">
              <span className="eyebrow">Tiendas</span>
              <span className="font-display text-xl tabular">{latest.length}</span>
            </div>
          </div>
        </aside>
      </section>

      <div className="hairline reveal reveal-2" />

      {/* HISTÓRICO */}
      <section className="reveal reveal-3">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <p className="eyebrow">Sección 02</p>
            <h2 className="font-display text-3xl md:text-4xl mt-1 leading-tight">
              Historia de precios
            </h2>
          </div>
          <p className="eyebrow text-right">
            últimos 180 días
            <br />
            <span className="text-muted text-[9px]">por tienda · CLP</span>
          </p>
        </div>

        <div className="bg-bone-soft/40 border border-rule p-6">
          {history.length > 0 ? (
            <PriceChart history={history} />
          ) : (
            <p className="font-display italic text-center text-muted py-12 text-xl">
              Aún no hay suficiente historia. Vuelve mañana — la recolección es nocturna.
            </p>
          )}
        </div>
      </section>

      {/* COMPARATIVA POR RETAILER */}
      <section className="reveal reveal-4">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <p className="eyebrow">Sección 03</p>
            <h2 className="font-display text-3xl md:text-4xl mt-1 leading-tight">
              Tiendas que lo venden
            </h2>
          </div>
          <p className="eyebrow">{latest.length} de 10</p>
        </div>

        <div className="overflow-x-auto">
          <table className="table-editorial">
            <thead>
              <tr>
                <th className="w-[28%]">Tienda</th>
                <th>Precio</th>
                <th>Antes</th>
                <th>Diferencia vs. mín.</th>
                <th>Actualizado</th>
                <th className="text-right">Acción</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => {
                const isMin = row.price_clp === min;
                const delta = min ? row.price_clp - min : 0;
                return (
                  <tr key={row.retailer + row.url}>
                    <td>
                      <div className="flex items-center gap-3">
                        <span
                          className="chip-retailer"
                          style={
                            {
                              ["--chip-color" as string]: retailerColor(row.retailer),
                            } as React.CSSProperties
                          }
                        >
                          {retailerLabel(row.retailer)}
                        </span>
                        {isMin && <span className="badge-min shimmer">mín</span>}
                      </div>
                    </td>
                    <td>
                      <span className="font-display text-2xl tabular">
                        {formatCLP(row.price_clp)}
                      </span>
                    </td>
                    <td className="text-muted line-through font-mono text-sm tabular">
                      {row.list_price_clp ? formatCLP(row.list_price_clp) : ""}
                    </td>
                    <td className="font-mono text-sm tabular">
                      {delta > 0 ? (
                        <span className="text-burgundy">+{formatCLP(delta)}</span>
                      ) : (
                        <span className="text-gold-deep">— base</span>
                      )}
                    </td>
                    <td className="font-mono text-xs text-muted tabular">
                      {new Date(row.scraped_at).toLocaleDateString("es-CL", {
                        day: "2-digit",
                        month: "short",
                      })}
                    </td>
                    <td className="text-right">
                      <a
                        href={row.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="eyebrow link-editorial"
                      >
                        ir a la tienda →
                      </a>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ALERTA */}
      <section className="reveal reveal-4">
        <div className="grid grid-cols-12 gap-6 lg:gap-12 border-t border-ink pt-10">
          <div className="col-span-12 lg:col-span-5">
            <p className="eyebrow">Sección 04</p>
            <h2 className="font-display text-3xl md:text-4xl mt-1 leading-tight">
              Vigilar este perfume
            </h2>
            <p className="font-display italic text-xl text-ink-soft mt-4 max-w-md">
              Te enviamos un Telegram en el instante exacto en que cualquiera de las{" "}
              {latest.length} tiendas baje al precio que definas.
            </p>
          </div>
          <div className="col-span-12 lg:col-span-7">
            <AlertForm perfumeId={perfume.id} minNow={min} />
          </div>
        </div>
      </section>
    </div>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="eyebrow text-[10px] mb-1">{label}</p>
      <p className="font-display text-xl tracking-tight">{value}</p>
    </div>
  );
}
