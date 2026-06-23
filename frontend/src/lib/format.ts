export const fmtZar = new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR" });
export const fmtNum = new Intl.NumberFormat("en-ZA");
export const fmtCompactNum = new Intl.NumberFormat("en-ZA", {
  notation: "compact",
  maximumFractionDigits: 1,
});
export const fmtCompactZar = new Intl.NumberFormat("en-ZA", {
  style: "currency",
  currency: "ZAR",
  notation: "compact",
  maximumFractionDigits: 1,
});
export const fmtCredits = new Intl.NumberFormat("en-ZA", {
  maximumFractionDigits: 2,
});
export const fmtCompactCredits = new Intl.NumberFormat("en-ZA", {
  notation: "compact",
  maximumFractionDigits: 1,
});
export const fmtRate = new Intl.NumberFormat("en-ZA", {
  maximumFractionDigits: 4,
});

export function credits(value: number) {
  return `${fmtCredits.format(value)} credits`;
}

export function compactCredits(value: number) {
  return `${fmtCompactCredits.format(value)} credits`;
}

export function formatLimitValue(value: number, metric?: string) {
  return metric === "total_credits" ? compactCredits(value) : `${fmtCompactNum.format(value)} tokens`;
}

export function formatDateTime(value?: string) {
  if (!value) return "Not ready";
  return new Date(value).toLocaleString();
}

export function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}
