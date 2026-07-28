export const VIRTUAL_THING_PREFIX = 'virtual:things:';
export const VIRTUAL_RECORD_THING_PREFIX = 'virtual:records:';
export const AUTO_DISCOVERED_SOURCE = 'auto-discovered';

export function isVirtualThingId(id: string | null | undefined): boolean {
  return typeof id === 'string' && id.startsWith(VIRTUAL_THING_PREFIX);
}

export function isVirtualRecordThingId(id: string | null | undefined): boolean {
  return typeof id === 'string' && id.startsWith(VIRTUAL_RECORD_THING_PREFIX);
}

export function isAutoDiscoveredSource(source: string | null | undefined): boolean {
  return source === AUTO_DISCOVERED_SOURCE;
}
