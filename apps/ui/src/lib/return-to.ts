export function getFirstSearchParam(
  value: string | string[] | undefined,
): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function getLocalReturnTo(
  returnTo: string | undefined,
  fallback: string,
) {
  if (!returnTo || !returnTo.startsWith('/') || returnTo.startsWith('//')) {
    return fallback;
  }

  return returnTo;
}

export function withReturnTo(href: string, returnTo: string | undefined) {
  if (!returnTo) {
    return href;
  }

  const separator = href.includes('?') ? '&' : '?';
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`;
}

export function isCollectionReturnTo(returnTo: string, collectionPath: string) {
  return (
    returnTo === collectionPath || returnTo.startsWith(`${collectionPath}?`)
  );
}
