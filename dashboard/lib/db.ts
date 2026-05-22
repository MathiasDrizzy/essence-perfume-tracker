import postgres from "postgres";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error("DATABASE_URL env var is required");
}

// Convert SQLAlchemy URL prefix to plain postgres://
const normalized = connectionString.replace(/^postgresql\+psycopg:\/\//, "postgresql://");

declare global {
  var __pg: ReturnType<typeof postgres> | undefined;
}

export const sql = global.__pg ?? postgres(normalized, { prepare: false });
if (process.env.NODE_ENV !== "production") global.__pg = sql;
