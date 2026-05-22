import Link from "next/link";
import { sql } from "@/lib/db";
import { formatCLP, retailerLabel, retailerColor } from "@/lib/utils";
import Combobox from "@/components/Combobox";
import SearchBox from "@/components/SearchBox";

export const dynamic = "force-dynamic";

type Row = {
  id: number;
  brand: string;
  name: string;
  concentration: string | null;
  volume_ml: number;
  gender: string | null;
  min_price: number;
  min_retailer: string;
  retailers: number;
  spread_pct: number | null;
};

type Stats = {
  perfumes: number;
  listings: number;
  retailers: number;
  last_scrape: string | null;
};

type SearchParams = {
  q?: string;
  brand?: string;
  ml?: string;
  gender?: string;
  conc?: string;
  page?: string;
  sort?: string;
};

const PAGE_SIZE = 30;

async function getFilters() {
  const [brands, vols] = await Promise.all([
    sql<{ brand: string }[]>`
      SELECT brand FROM (SELECT DISTINCT brand FROM perfumes) t
      ORDER BY brand COLLATE "C"
    `,
    sql<{ volume_ml: number }[]>`
      SELECT DISTINCT volume_ml FROM perfumes
      WHERE volume_ml IN (30,50,75,90,100,125,150,200,250) ORDER BY volume_ml
    `,
  ]);
  return { brands: brands.map((b) => b.brand), volumes: vols.map((v) => v.volume_ml) };
}

async function getStats(): Promise<Stats> {
  const [r] = await sql<Stats[]>`
    SELECT
      (SELECT count(*)::int FROM perfumes) AS perfumes,
      (SELECT count(*)::int FROM listings WHERE active) AS listings,
      (SELECT count(DISTINCT retailer)::int FROM listings WHERE active) AS retailers,
      (SELECT max(scraped_at)::text FROM price_history) AS last_scrape
  `;
  return r;
}

async function getPerfumes(params: SearchParams) {
  const page = Math.max(1, Number(params.page) || 1);
  const offset = (page - 1) * PAGE_SIZE;
  const sort = params.sort || "spread";

  const q = params.q?.trim() || null;
  const brand = params.brand?.trim() || null;
  const ml = params.ml ? Number(params.ml) : null;
  const gender = params.gender?.trim() || null;
  const conc = params.conc?.trim() || null;

  const orderBy =
    sort === "price-asc"
      ? sql`min_price ASC NULLS LAST`
      : sort === "price-desc"
        ? sql`min_price DESC NULLS LAST`
        : sort === "name"
          ? sql`p.brand ASC, p.name ASC`
          : sort === "retailers"
            ? sql`retailers DESC, spread_pct DESC NULLS LAST`
            : sql`spread_pct DESC NULLS LAST, retailers DESC`;

  const rows = await sql<Row[]>`
    WITH latest AS (
      SELECT DISTINCT ON (l.id) l.perfume_id, l.retailer, ph.price_clp
      FROM listings l
      JOIN price_history ph ON ph.listing_id = l.id
      WHERE l.active AND ph.price_clp > 100
      ORDER BY l.id, ph.scraped_at DESC
    ),
    agg AS (
      SELECT
        perfume_id,
        MIN(price_clp) AS min_price,
        (ARRAY_AGG(retailer ORDER BY price_clp ASC))[1] AS min_retailer,
        COUNT(DISTINCT retailer) AS retailers,
        MAX(price_clp) AS max_price
      FROM latest
      GROUP BY perfume_id
    )
    SELECT p.id, p.brand, p.name, p.concentration, p.volume_ml, p.gender,
      a.min_price, a.min_retailer, a.retailers,
      CASE WHEN a.max_price > 0 AND a.retailers > 1
           THEN ROUND((1.0 - a.min_price::numeric / a.max_price) * 100)::int
           ELSE NULL END AS spread_pct
    FROM perfumes p
    JOIN agg a ON a.perfume_id = p.id
    WHERE
      (${q}::text IS NULL OR (p.brand ILIKE '%' || ${q} || '%' OR p.name ILIKE '%' || ${q} || '%'))
      AND (${brand}::text IS NULL OR p.brand = ${brand})
      AND (${ml}::int IS NULL OR p.volume_ml = ${ml})
      AND (${gender}::text IS NULL OR p.gender = ${gender})
      AND (${conc}::text IS NULL OR p.concentration = ${conc})
    ORDER BY ${orderBy}
    LIMIT ${PAGE_SIZE} OFFSET ${offset}
  `;

  return { rows, page };
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const [{ brands, volumes }, { rows, page }, stats] = await Promise.all([
    getFilters(),
    getPerfumes(params),
    getStats(),
  ]);

  const lastScrape = stats.last_scrape
    ? new Date(stats.last_scrape).toLocaleDateString("es-CL", {
        day: "2-digit",
        month: "long",
      })
    : "—";

  return (
    <div className="space-y-14">
      {/* HERO EDITORIAL */}
      <section className="grid grid-cols-12 gap-6 lg:gap-10 items-end reveal reveal-1">
        <div className="col-span-12 lg:col-span-8">
          <p className="eyebrow mb-6">№ 001 · Catálogo vivo · Mayo 2026</p>
          <h1 className="font-display text-[clamp(48px,8vw,128px)] leading-[0.9] tracking-[-0.04em] font-light">
            Diez tiendas.
            <br className="hidden md:inline" /> Un catálogo.
            <br className="hidden md:inline" />{" "}
            <em className="italic font-normal text-gold-deep">El mejor precio.</em>
          </h1>
          <p className="font-display text-xl md:text-2xl italic text-ink-soft mt-8 max-w-2xl leading-snug">
            Comparamos cada noche los precios en las principales tiendas chilenas de perfumería
            para que compres en la tienda correcta, al precio correcto.
          </p>
        </div>

        <aside className="col-span-12 lg:col-span-4">
          <div className="border-t border-ink pt-4 space-y-3">
            <Metric label="Perfumes catalogados" value={stats.perfumes.toLocaleString("es-CL")} />
            <Metric label="Listings activos" value={stats.listings.toLocaleString("es-CL")} />
            <Metric label="Tiendas conectadas" value={String(stats.retailers)} />
            <Metric label="Último scrape" value={lastScrape} />
          </div>
        </aside>
      </section>

      <div className="hairline reveal reveal-2" />

      {/* FILTROS */}
      <section className="reveal reveal-2">
        <div className="flex items-baseline justify-between mb-6">
          <p className="eyebrow">Sección 02 · Filtros del catálogo</p>
          <p className="eyebrow">{rows.length} resultados visibles</p>
        </div>

        <form className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-x-8 gap-y-5">
          <SearchBox defaultValue={params.q || ""} />
          <Combobox
            name="brand"
            label="Marca"
            defaultValue={params.brand || ""}
            placeholder="Escribe una marca…"
            options={brands.map((b) => ({ value: b, label: b }))}
          />
          <FilterField label="Volumen">
            <select name="ml" defaultValue={params.ml || ""} className="field">
              <option value="">Todos</option>
              {volumes.map((v) => (
                <option key={v} value={v}>
                  {v} ml
                </option>
              ))}
            </select>
          </FilterField>
          <FilterField label="Concentración">
            <select name="conc" defaultValue={params.conc || ""} className="field">
              <option value="">Todas</option>
              <option value="PARFUM">Parfum</option>
              <option value="EDP">Eau de Parfum</option>
              <option value="EDT">Eau de Toilette</option>
              <option value="EDC">Eau de Cologne</option>
            </select>
          </FilterField>
          <FilterField label="Género">
            <select name="gender" defaultValue={params.gender || ""} className="field">
              <option value="">Cualquiera</option>
              <option value="Hombre">Hombre</option>
              <option value="Mujer">Mujer</option>
              <option value="Unisex">Unisex</option>
            </select>
          </FilterField>
          <FilterField label="Orden" colSpan="col-span-2">
            <select name="sort" defaultValue={params.sort || "spread"} className="field">
              <option value="spread">Mayor ahorro entre tiendas</option>
              <option value="retailers">Más tiendas que lo venden</option>
              <option value="price-asc">Precio mínimo ↑</option>
              <option value="price-desc">Precio mínimo ↓</option>
              <option value="name">Alfabético</option>
            </select>
          </FilterField>
          <div className="col-span-2 md:col-span-1 flex items-end">
            <button type="submit" className="btn-gold w-full">
              Filtrar
            </button>
          </div>
          <div className="col-span-2 md:col-span-1 flex items-end">
            <Link
              href="/"
              className="eyebrow text-[10px] hover:text-gold-deep transition-colors"
            >
              Limpiar filtros →
            </Link>
          </div>
        </form>
      </section>

      <div className="hairline" />

      {/* TABLA EDITORIAL */}
      <section className="reveal reveal-3">
        <div className="flex items-baseline justify-between mb-6">
          <p className="eyebrow">Sección 03 · Edición {String(page).padStart(3, "0")}</p>
          <p className="eyebrow tabular">página {page}</p>
        </div>

        <div className="overflow-x-auto">
          <table className="table-editorial">
            <thead>
              <tr>
                <th className="w-[44%]">Perfume</th>
                <th>Medida</th>
                <th>Tiendas</th>
                <th title="Cuánto ahorras eligiendo la tienda más barata respecto de la más cara">
                  Ahorro %
                </th>
                <th className="text-right">Mejor precio</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id}>
                  <td>
                    <div className="flex items-baseline gap-3">
                      <span className="font-mono text-xs text-muted tabular w-8">
                        {String((page - 1) * PAGE_SIZE + i + 1).padStart(3, "0")}
                      </span>
                      <div>
                        <p className="eyebrow text-[10px] text-gold-deep mb-1">
                          {r.brand}
                        </p>
                        <Link
                          href={`/perfume/${r.id}`}
                          className="font-display text-xl md:text-2xl leading-tight tracking-tight hover:text-gold-deep transition-colors"
                        >
                          {r.name}
                        </Link>
                      </div>
                    </div>
                  </td>
                  <td className="font-mono text-xs tabular text-ink-soft">
                    {r.volume_ml} ml
                    {r.concentration && (
                      <span className="block text-muted mt-1">{r.concentration}</span>
                    )}
                  </td>
                  <td>
                    <span className="font-display text-2xl tabular">{r.retailers}</span>
                    <span className="text-muted text-xs ml-1">/10</span>
                  </td>
                  <td>
                    {r.spread_pct != null && r.spread_pct > 0 ? (
                      <SpreadGauge pct={r.spread_pct} />
                    ) : (
                      <span className="text-muted font-mono text-xs">—</span>
                    )}
                  </td>
                  <td className="text-right">
                    <p className="font-display text-2xl tabular leading-none">
                      {formatCLP(r.min_price)}
                    </p>
                    <span
                      className="chip-retailer mt-2"
                      style={
                        {
                          ["--chip-color" as string]: retailerColor(r.min_retailer),
                        } as React.CSSProperties
                      }
                    >
                      {retailerLabel(r.min_retailer)}
                    </span>
                  </td>
                  <td className="text-right">
                    <Link
                      href={`/perfume/${r.id}`}
                      className="eyebrow text-[10px] hover:text-gold-deep transition-colors"
                    >
                      ver →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {rows.length === 0 && (
          <div className="text-center py-20">
            <p className="font-display italic text-2xl text-muted">
              Sin coincidencias. Ajusta los filtros.
            </p>
          </div>
        )}
      </section>

      {/* PAGINACIÓN */}
      <nav className="flex items-center justify-between border-t border-ink pt-6">
        {page > 1 ? (
          <Link
            href={{ pathname: "/", query: { ...params, page: String(page - 1) } }}
            className="eyebrow link-editorial"
          >
            ← Página anterior
          </Link>
        ) : (
          <span />
        )}
        <span className="font-mono text-xs text-muted tabular">
          {String(page).padStart(3, "0")} / ∞
        </span>
        {rows.length === PAGE_SIZE ? (
          <Link
            href={{ pathname: "/", query: { ...params, page: String(page + 1) } }}
            className="eyebrow link-editorial"
          >
            Página siguiente →
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="eyebrow text-[10px]">{label}</span>
      <span className="font-display text-2xl tabular tracking-tight">{value}</span>
    </div>
  );
}

function FilterField({
  label,
  children,
  colSpan = "",
}: {
  label: string;
  children: React.ReactNode;
  colSpan?: string;
}) {
  return (
    <label className={`block ${colSpan}`}>
      <span className="eyebrow text-[10px] block mb-2">{label}</span>
      {children}
    </label>
  );
}

function SpreadGauge({ pct }: { pct: number }) {
  const intensity = Math.min(100, pct);
  return (
    <div className="flex items-center gap-2">
      <span className="font-display text-xl tabular text-burgundy">{pct}%</span>
      <div className="w-16 h-[2px] bg-rule relative">
        <div
          className="absolute inset-y-0 left-0 bg-burgundy"
          style={{ width: `${intensity}%` }}
        />
      </div>
    </div>
  );
}
