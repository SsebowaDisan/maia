type UnknownRecord = Record<string, unknown>;

function toRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" ? (value as UnknownRecord) : {};
}

function readNestedRecord(record: UnknownRecord, key: string): UnknownRecord {
  return toRecord(record[key]);
}

function readEventPayload(input: { data?: unknown; metadata?: unknown } | null | undefined): UnknownRecord {
  const data = toRecord(input?.data);
  const metadata = toRecord(input?.metadata);
  const nestedData = readNestedRecord(data, "data");
  const nestedMetadata = readNestedRecord(metadata, "data");
  return {
    ...nestedMetadata,
    ...metadata,
    ...nestedData,
    ...data,
  };
}

export { readEventPayload, toRecord };
