export function parseBooleanEnv(
  value: string | undefined,
  name: string
): boolean {
  if (value === undefined) return false;

  const normalized = value.trim().toLowerCase();
  if (normalized === 'true' || normalized === '1') return true;
  if (normalized === 'false' || normalized === '0') return false;

  console.warn(`Invalid ${name} value "${value}"; defaulting to false`);
  return false;
}
