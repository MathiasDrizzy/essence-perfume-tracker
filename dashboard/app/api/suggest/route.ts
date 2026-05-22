import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const dynamic = "force-dynamic";

type Suggestion =
  | { kind: "brand"; brand: string; count: number }
  | { kind: "perfume"; id: number; brand: string; name: string; volume_ml: number; concentration: string | null };

export async function GET(req: NextRequest) {
  const q = (req.nextUrl.searchParams.get("q") || "").trim();
  if (q.length < 1) return NextResponse.json({ items: [] });

  // Marcas que empiezan o contienen el query, top 5 por # de productos
  const brands = await sql<{ brand: string; count: number }[]>`
    SELECT brand, count(*)::int as count
    FROM perfumes
    WHERE brand ILIKE ${q + "%"} OR brand ILIKE ${"%" + q + "%"}
    GROUP BY brand
    ORDER BY (brand ILIKE ${q + "%"}) DESC, count(*) DESC
    LIMIT 5
  `;

  // Perfumes cuyo brand+name matchee, top 8 por # de retailers activos
  const perfumes = await sql<{
    id: number;
    brand: string;
    name: string;
    volume_ml: number;
    concentration: string | null;
    retailers: number;
  }[]>`
    SELECT p.id, p.brand, p.name, p.volume_ml, p.concentration,
      (SELECT count(DISTINCT l.retailer)::int FROM listings l WHERE l.perfume_id = p.id AND l.active) AS retailers
    FROM perfumes p
    WHERE p.brand ILIKE ${"%" + q + "%"} OR p.name ILIKE ${"%" + q + "%"}
    ORDER BY
      (p.name ILIKE ${q + "%"}) DESC,
      (p.brand ILIKE ${q + "%"}) DESC,
      (SELECT count(DISTINCT l.retailer) FROM listings l WHERE l.perfume_id = p.id AND l.active) DESC NULLS LAST
    LIMIT 8
  `;

  const items: Suggestion[] = [
    ...brands.map((b) => ({ kind: "brand" as const, brand: b.brand, count: b.count })),
    ...perfumes.map((p) => ({
      kind: "perfume" as const,
      id: p.id,
      brand: p.brand,
      name: p.name,
      volume_ml: p.volume_ml,
      concentration: p.concentration,
    })),
  ];

  return NextResponse.json({ items });
}
