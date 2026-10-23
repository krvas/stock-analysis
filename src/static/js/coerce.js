/** Value coercion shared by models and controllers. No DOM, no globals. */

/**
 * Coerce an arbitrary value to a finite number or null.
 *
 * - null/undefined/"" -> null
 * - a number -> itself, unless NaN (-> null)
 * - anything else -> Number(value), or null if that isn't finite/parseable
 */
export function coerceNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "number") {
    return Number.isNaN(value) ? null : value;
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}
