/**
 * Structured output — enforce typed responses from LLMs.
 *
 * Define a schema, get validated output. Auto-repairs common issues:
 * - Strips markdown code fences
 * - Extracts JSON from surrounding text
 * - Validates required fields
 * - Provides typed fallback on parse failure
 */

export interface FieldDef {
  type: "string" | "number" | "boolean" | "array" | "object";
  required?: boolean;
  description?: string;
  default?: any;
  items?: FieldDef;
  properties?: Record<string, FieldDef>;
  enum?: any[];
}

export interface OutputSchema {
  fields: Record<string, FieldDef>;
  description?: string;
}

/**
 * Build a schema instruction string for the LLM system prompt.
 * Tells the LLM exactly what JSON structure to return.
 */
export function schemaToPrompt(schema: OutputSchema): string {
  const example: Record<string, any> = {};
  for (const [key, def] of Object.entries(schema.fields)) {
    example[key] = fieldExample(def);
  }

  const fieldDocs = Object.entries(schema.fields)
    .map(([key, def]) => {
      const req = def.required !== false ? "(required)" : "(optional)";
      const desc = def.description ? ` — ${def.description}` : "";
      const enumStr = def.enum ? ` [one of: ${def.enum.join(", ")}]` : "";
      return `  "${key}": ${def.type}${enumStr} ${req}${desc}`;
    })
    .join("\n");

  return (
    "\n\nYou MUST return valid JSON matching this schema:\n"
    + `{\n${fieldDocs}\n}\n\n`
    + `Example: ${JSON.stringify(example)}\n`
    + "Return ONLY the JSON object. No markdown, no explanation."
  );
}

/**
 * Validate and repair LLM output against a schema.
 * Returns the validated object or the fallback if repair fails.
 */
export function validateOutput<T extends Record<string, any>>(
  raw: string,
  schema: OutputSchema,
  fallback: T,
): { data: T; valid: boolean; repairs: string[] } {
  const repairs: string[] = [];

  // Step 1: Extract JSON from raw text
  let parsed = extractJson(raw);
  if (!parsed) {
    return { data: fallback, valid: false, repairs: ["Failed to extract JSON from response"] };
  }

  // Step 2: Validate and repair each field
  for (const [key, def] of Object.entries(schema.fields)) {
    const value = parsed[key];

    // Missing required field
    if (value === undefined || value === null) {
      if (def.required !== false) {
        if (def.default !== undefined) {
          parsed[key] = def.default;
          repairs.push(`Missing required field "${key}" — used default`);
        } else if (key in fallback) {
          parsed[key] = (fallback as any)[key];
          repairs.push(`Missing required field "${key}" — used fallback`);
        }
      }
      continue;
    }

    // Type checking and coercion
    if (def.type === "number" && typeof value === "string") {
      const num = Number(value);
      if (!isNaN(num)) { parsed[key] = num; repairs.push(`Coerced "${key}" from string to number`); }
    }
    if (def.type === "boolean" && typeof value === "string") {
      parsed[key] = value.toLowerCase() === "true" || value === "1";
      repairs.push(`Coerced "${key}" from string to boolean`);
    }
    if (def.type === "array" && !Array.isArray(value)) {
      parsed[key] = [value];
      repairs.push(`Wrapped "${key}" in array`);
    }

    // Enum validation
    if (def.enum && !def.enum.includes(parsed[key])) {
      const closest = findClosestEnum(String(parsed[key]), def.enum);
      if (closest !== null) {
        parsed[key] = closest;
        repairs.push(`Corrected "${key}" enum value to "${closest}"`);
      }
    }
  }

  return { data: parsed as T, valid: repairs.length === 0, repairs };
}

/**
 * Define a schema with a fluent builder.
 */
export function schema(description?: string) {
  const fields: Record<string, FieldDef> = {};
  const builder = {
    string(name: string, desc?: string, opts?: { required?: boolean; enum?: string[]; default?: string }) {
      fields[name] = { type: "string", description: desc, required: opts?.required, enum: opts?.enum, default: opts?.default };
      return builder;
    },
    number(name: string, desc?: string, opts?: { required?: boolean; default?: number }) {
      fields[name] = { type: "number", description: desc, required: opts?.required, default: opts?.default };
      return builder;
    },
    boolean(name: string, desc?: string, opts?: { required?: boolean; default?: boolean }) {
      fields[name] = { type: "boolean", description: desc, required: opts?.required, default: opts?.default };
      return builder;
    },
    array(name: string, desc?: string, opts?: { required?: boolean }) {
      fields[name] = { type: "array", description: desc, required: opts?.required };
      return builder;
    },
    build(): OutputSchema { return { fields, description }; },
  };
  return builder;
}

// ── Internals ────────────────────────────────────────────────────────────────

function extractJson(raw: string): Record<string, any> | null {
  let text = raw.trim();
  // Strip code fences
  if (text.startsWith("```")) {
    const first = text.indexOf("\n");
    if (first >= 0) text = text.slice(first + 1);
    if (text.endsWith("```")) text = text.slice(0, -3);
    text = text.trim();
  }
  // Direct parse
  try { return JSON.parse(text); } catch { /* continue */ }
  // Extract first JSON object
  const m = text.match(/\{[\s\S]*\}/);
  if (m) { try { return JSON.parse(m[0]); } catch { /* continue */ } }
  return null;
}

function fieldExample(def: FieldDef): any {
  if (def.default !== undefined) return def.default;
  if (def.enum?.length) return def.enum[0];
  switch (def.type) {
    case "string": return "";
    case "number": return 0;
    case "boolean": return false;
    case "array": return [];
    case "object": return {};
    default: return null;
  }
}

function findClosestEnum(value: string, enums: any[]): any {
  const lower = value.toLowerCase();
  for (const e of enums) {
    if (String(e).toLowerCase() === lower) return e;
  }
  for (const e of enums) {
    if (String(e).toLowerCase().includes(lower) || lower.includes(String(e).toLowerCase())) return e;
  }
  return enums[0] ?? null;
}