import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCLP(value: number | null | undefined): string {
  if (value == null) return "—";
  return `$${value.toLocaleString("es-CL")}`;
}

export function formatDate(d: Date | string): string {
  const date = typeof d === "string" ? new Date(d) : d;
  return date.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
}

const RETAILER_LABELS: Record<string, string> = {
  paris: "Paris",
  ripley: "Ripley",
  falabella: "Falabella",
  mercadolibre: "MercadoLibre",
  sairam: "Sairam",
  silkperfumes: "Silk Perfumes",
  productosdelujo: "Productos de Lujo",
  multimarcasperfumes: "Multimarcas",
  alishaperfumes: "Alisha Perfumes",
  eliteperfumes: "Elite Perfumes",
};

const RETAILER_COLORS: Record<string, string> = {
  paris: "#B88643",
  ripley: "#772626",
  falabella: "#4A5234",
  mercadolibre: "#C19A5B",
  sairam: "#5F4F3D",
  silkperfumes: "#8A6029",
  productosdelujo: "#9D5C2F",
  multimarcasperfumes: "#6B4E2B",
  alishaperfumes: "#52462F",
  eliteperfumes: "#7C5A2C",
};

export function retailerLabel(key: string): string {
  return RETAILER_LABELS[key] ?? key;
}

export function retailerColor(key: string): string {
  return RETAILER_COLORS[key] ?? "#847766";
}
