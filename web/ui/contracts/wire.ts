// Field readers shared by the catalog and example parsers. Each takes the raw wire
// value and the dotted path it was read from, and throws with that path when the value
// is not what the contract says. Nothing here knows a document kind.

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

export type JsonObject = { readonly [key: string]: JsonValue };

export function object(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

export function array(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

export function list<T>(
  value: unknown,
  label: string,
  read: (entry: unknown, label: string) => T,
): readonly T[] {
  return Object.freeze(array(value, label).map((entry, index) => read(entry, `${label}[${index}]`)));
}

export function record<T>(
  value: unknown,
  label: string,
  read: (entry: unknown, label: string) => T,
): Readonly<Record<string, T>> {
  const out: Record<string, T> = {};
  for (const [key, entry] of Object.entries(object(value, label))) {
    out[key] = read(entry, `${label}.${key}`);
  }
  return Object.freeze(out);
}

export function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

/** A string that may be empty, such as a note nobody wrote. */
export function anyText(value: unknown, label: string): string {
  if (typeof value !== "string") throw new Error(`${label} must be a string`);
  return value;
}

export function textOrNull(value: unknown, label: string): string | null {
  if (value === null || value === undefined) return null;
  return text(value, label);
}

export function number(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
  return value;
}

export function numberOrNull(value: unknown, label: string): number | null {
  if (value === null || value === undefined) return null;
  return number(value, label);
}

export function integer(value: unknown, label: string, minimum = 0): number {
  const result = number(value, label);
  if (!Number.isInteger(result) || result < minimum) {
    throw new Error(`${label} must be an integer of at least ${minimum}`);
  }
  return result;
}

export function integerOrNull(value: unknown, label: string, minimum = 0): number | null {
  if (value === null || value === undefined) return null;
  return integer(value, label, minimum);
}

export function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
  return value;
}

export function digest(value: unknown, label: string): string {
  const result = text(value, label);
  if (!/^[a-f0-9]{64}$/.test(result)) throw new Error(`${label} must be a SHA-256 digest`);
  return result;
}

export function oneOf<const T extends string>(
  value: unknown,
  label: string,
  allowed: readonly T[],
): T {
  if ((allowed as readonly unknown[]).includes(value)) return value as T;
  throw new Error(`${label} must be one of ${allowed.join(", ")}`);
}

/** Opaque JSON a consumer interprets itself, checked only for being JSON. */
export function json(value: unknown, label: string): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") return number(value, label);
  if (Array.isArray(value)) return list(value, label, json);
  if (typeof value !== "object") throw new Error(`${label} must be JSON`);
  return record(value, label, json);
}

export function jsonObject(value: unknown, label: string): JsonObject {
  return record(value, label, json);
}

export function jsonObjectOrNull(value: unknown, label: string): JsonObject | null {
  if (value === null || value === undefined) return null;
  return jsonObject(value, label);
}

/** Refuse a document whose envelope is not the one version this parser reads. */
export function envelope(
  value: unknown,
  kind: string,
  schemaVersion: number,
  refusal: string,
): Record<string, unknown> {
  const root = object(value, kind);
  if (root.kind !== kind || root.schema_version !== schemaVersion) throw new Error(refusal);
  return root;
}
