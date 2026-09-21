/**
 * Shared formatting and unit helpers for financial statement views.
 */

export const UNIT_OPTIONS = {
  billions: { scale: 1e9, label: "billions" },
  millions: { scale: 1e6, label: "millions" },
  thousands: { scale: 1e3, label: "thousands" },
  units: { scale: 1, label: "units" },
};

let CURRENT_UNIT = "millions";

export function getStatementUnit() {
  return window.STATEMENT_UNIT || CURRENT_UNIT;
}

export function setStatementUnit(key) {
  if (UNIT_OPTIONS[key]) {
    CURRENT_UNIT = key;
    window.STATEMENT_UNIT = key;
  }
}

window.getStatementUnit = getStatementUnit;
window.setStatementUnit = setStatementUnit;

export function getUnitLabel(unitKey) {
  const key = unitKey || getStatementUnit();
  return (UNIT_OPTIONS[key] || UNIT_OPTIONS.millions).label;
}

export function formatNumber(value, unitKey) {
  if (value === null || value === undefined) {
    return '<span class="empty">—</span>';
  }
  const unit = UNIT_OPTIONS[unitKey] || UNIT_OPTIONS.millions;
  const scaled = value / unit.scale;
  return scaled.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function computeDifference(latest, previous) {
  if (
    latest === null ||
    latest === undefined ||
    previous === null ||
    previous === undefined
  ) {
    return null;
  }
  return latest - previous;
}
