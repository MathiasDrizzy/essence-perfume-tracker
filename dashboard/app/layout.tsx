import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "ESSENCE · Catálogo de Perfumería Chilena",
  description:
    "Comparador de precios e histórico para 10 perfumerías y retailers de Chile.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-CL">
      <body className="min-h-screen bg-bone text-ink">
        <header className="border-b border-ink/90 bg-bone/95 sticky top-0 z-30 backdrop-blur-sm">
          <div className="max-w-[1400px] mx-auto px-6 lg:px-12 py-4 flex items-center justify-between gap-8">
            <Link href="/" className="group flex items-center gap-3">
              <Wordmark />
              <div className="hidden sm:flex flex-col leading-none">
                <span className="font-display text-[22px] tracking-[-0.04em] font-medium leading-none">
                  ESSENCE
                </span>
                <span className="eyebrow mt-1 text-[9px]">
                  Catálogo de Perfumería · Chile
                </span>
              </div>
            </Link>

            <nav className="flex items-center gap-8">
              <Link href="/" className="link-editorial eyebrow text-[11px]">
                Catálogo
              </Link>
              <Link href="/alerts" className="link-editorial eyebrow text-[11px]">
                Alertas
              </Link>
              <a
                href="https://github.com"
                className="link-editorial eyebrow text-[11px] hidden md:inline"
                target="_blank"
                rel="noopener"
              >
                Acerca
              </a>
            </nav>

            <div className="hidden md:flex items-center gap-3 text-right">
              <span className="eyebrow text-[10px]">Santiago, CL</span>
              <span className="font-mono text-[10px] text-muted">
                {new Intl.DateTimeFormat("es-CL", {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                }).format(new Date())}
              </span>
            </div>
          </div>
        </header>

        <main className="max-w-[1400px] mx-auto px-6 lg:px-12 py-10">{children}</main>

        <footer className="border-t border-rule mt-24">
          <div className="max-w-[1400px] mx-auto px-6 lg:px-12 py-10 grid grid-cols-1 md:grid-cols-3 gap-8">
            <div>
              <Wordmark className="w-8 h-8" />
              <p className="font-display italic text-lg mt-3 leading-tight">
                El catálogo vivo de la perfumería chilena.
              </p>
            </div>
            <div className="text-sm text-ink-soft space-y-2">
              <p className="eyebrow text-ink mb-3">Retailers</p>
              <p>Paris · Ripley · Falabella · MercadoLibre</p>
              <p>Silk Perfumes · Productos de Lujo · Multimarcas</p>
              <p>Alisha · Elite Perfumes · Sairam</p>
            </div>
            <div className="text-sm text-ink-soft space-y-2 md:text-right">
              <p className="eyebrow text-ink mb-3">Actualizado</p>
              <p className="font-mono">Diariamente · 04:00 CLT</p>
              <p className="font-mono text-xs text-muted">v0.1 · 2026</p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}

function Wordmark({ className = "w-9 h-9" }: { className?: string }) {
  // Marca ESSENCE: cuadrado tinta con monograma "E" en serif francés.
  // Línea dorada inferior = trazo de la estela aromática.
  // Punto dorado sobre la E = la nota olfativa.
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <rect x="0" y="0" width="40" height="40" fill="rgb(var(--ink))" />
      <text
        x="20"
        y="28"
        textAnchor="middle"
        fontFamily="Fraunces, serif"
        fontWeight="400"
        fontSize="24"
        fill="rgb(var(--bone))"
        letterSpacing="-0.5"
      >
        E
      </text>
      <circle cx="29" cy="11" r="1.6" fill="rgb(var(--gold))" />
      <line
        x1="6"
        y1="34.5"
        x2="34"
        y2="34.5"
        stroke="rgb(var(--gold))"
        strokeWidth="1.5"
      />
    </svg>
  );
}
