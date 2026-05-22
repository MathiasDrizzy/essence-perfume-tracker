import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  if (!body) return NextResponse.json({ error: "invalid json" }, { status: 400 });

  const { perfume_id, target_price_clp, telegram_chat_id } = body;
  if (!perfume_id || !target_price_clp || !telegram_chat_id) {
    return NextResponse.json({ error: "missing fields" }, { status: 400 });
  }

  const [row] = await sql<{ id: number }[]>`
    INSERT INTO alerts (perfume_id, target_price_clp, telegram_chat_id)
    VALUES (${Number(perfume_id)}, ${Number(target_price_clp)}, ${String(telegram_chat_id)})
    RETURNING id
  `;
  return NextResponse.json({ id: row.id });
}

export async function DELETE(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const id = Number(searchParams.get("id"));
  if (!id) return NextResponse.json({ error: "missing id" }, { status: 400 });
  await sql`DELETE FROM alerts WHERE id = ${id}`;
  return NextResponse.json({ ok: true });
}
