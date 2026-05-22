"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";

export default function DeleteAlertButton({ id }: { id: number }) {
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  return (
    <button
      onClick={() => {
        if (!confirm("¿Eliminar esta vigilancia?")) return;
        startTransition(async () => {
          await fetch(`/api/alerts?id=${id}`, { method: "DELETE" });
          router.refresh();
        });
      }}
      disabled={pending}
      className="eyebrow text-[10px] text-burgundy hover:text-ink transition-colors disabled:opacity-40"
    >
      eliminar
    </button>
  );
}
