/**
 * Translation from JSON Schema, as MCP tools declare it, to WoT DataSchema.
 *
 * WoT's DataSchema is a subset of JSON Schema: it has no `$ref`, `anyOf`, `allOf`,
 * `additionalProperties` or conditional keywords. MCP servers routinely emit all of
 * them — anything generated from Pydantic or zod uses `$ref` plus `$defs`, and models
 * an optional field as `anyOf: [{type: X}, {type: "null"}]`.
 *
 * The translation is lossy by nature, so the untouched original travels alongside it
 * in the form's `mcp:inputSchema` and the client sends arguments through unmodified.
 * What is produced here exists so a reader — a person or the agent — can see the real
 * field names, types and constraints instead of an opaque object.
 */

/** Keywords WoT DataSchema shares with JSON Schema and that survive translation. */
const SCALAR_KEYWORDS = [
  'title',
  'description',
  'unit',
  'const',
  'default',
  'enum',
  'readOnly',
  'writeOnly',
  'format',
  'minimum',
  'maximum',
  'exclusiveMinimum',
  'exclusiveMaximum',
  'multipleOf',
  'minLength',
  'maxLength',
  'pattern',
  'contentEncoding',
  'contentMediaType',
  'minItems',
  'maxItems',
] as const;

const MAX_DEPTH = 12;

/**
 * Narrows an unknown value to a plain object.
 */
function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Follows a local `#/$defs/Name` or `#/definitions/Name` pointer within the root schema.
 *
 * Only local pointers are resolvable; a remote `$ref` has nothing to resolve against and
 * yields null so the caller can fall back to an untyped value.
 */
function resolveRef(ref: string, root: Record<string, unknown>): Record<string, unknown> | null {
  if (!ref.startsWith('#/')) {
    return null;
  }

  let current: unknown = root;
  for (const rawSegment of ref.slice(2).split('/')) {
    const segment = rawSegment.replace(/~1/g, '/').replace(/~0/g, '~');
    if (!isObject(current)) {
      return null;
    }
    current = current[segment];
  }

  return isObject(current) ? current : null;
}

/**
 * Reduces a union to the single branch WoT can express.
 *
 * `anyOf: [X, {type: "null"}]` is how an optional field arrives from most generators;
 * the null branch carries no information a DataSchema can hold, so the remaining branch
 * stands in for the union. A union of two real types has no WoT equivalent and is dropped.
 */
function collapseUnion(branches: unknown[]): Record<string, unknown> | null {
  const meaningful = branches.filter(
    (branch) => isObject(branch) && branch.type !== 'null' && !(Array.isArray(branch.type) && branch.type.length === 0),
  );

  return meaningful.length === 1 && isObject(meaningful[0]) ? meaningful[0] : null;
}

/**
 * Converts one JSON Schema node, resolving refs and unions against the root.
 */
function convert(node: unknown, root: Record<string, unknown>, depth: number): Record<string, unknown> {
  if (!isObject(node) || depth > MAX_DEPTH) {
    return {};
  }

  if (typeof node.$ref === 'string') {
    const resolved = resolveRef(node.$ref, root);
    return resolved ? convert(resolved, root, depth + 1) : {};
  }

  for (const unionKeyword of ['anyOf', 'oneOf'] as const) {
    const branches = node[unionKeyword];
    if (Array.isArray(branches)) {
      const collapsed = collapseUnion(branches);
      const merged = collapsed ? convert(collapsed, root, depth + 1) : {};
      // Keep any description that sat on the union itself rather than its branches.
      if (typeof node.description === 'string' && merged.description === undefined) {
        merged.description = node.description;
      }
      if (typeof node.title === 'string' && merged.title === undefined) {
        merged.title = node.title;
      }
      return merged;
    }
  }

  const result: Record<string, unknown> = {};

  // A type array such as ["string", "null"] is the same optionality trick as anyOf.
  if (typeof node.type === 'string') {
    result.type = node.type;
  } else if (Array.isArray(node.type)) {
    const concrete = node.type.filter((entry) => typeof entry === 'string' && entry !== 'null');
    if (concrete.length === 1) {
      result.type = concrete[0];
    }
  }

  for (const keyword of SCALAR_KEYWORDS) {
    if (node[keyword] !== undefined) {
      result[keyword] = node[keyword];
    }
  }

  if (isObject(node.properties)) {
    const properties: Record<string, unknown> = {};
    for (const [name, definition] of Object.entries(node.properties)) {
      properties[name] = convert(definition, root, depth + 1);
    }
    result.properties = properties;
    if (result.type === undefined) {
      result.type = 'object';
    }
  }

  if (Array.isArray(node.required)) {
    const required = node.required.filter((entry): entry is string => typeof entry === 'string');
    if (required.length > 0) {
      result.required = required;
    }
  }

  if (node.items !== undefined) {
    result.items = convert(node.items, root, depth + 1);
    if (result.type === undefined) {
      result.type = 'array';
    }
  }

  return result;
}

/**
 * Translates an MCP tool's JSON Schema into the closest WoT DataSchema.
 *
 * Returns an empty object when there is nothing translatable, which a caller should
 * treat as "no declared schema" rather than "an object with no fields".
 */
export function toDataSchema(schema: unknown): Record<string, unknown> {
  if (!isObject(schema)) {
    return {};
  }

  return convert(schema, schema, 0);
}
