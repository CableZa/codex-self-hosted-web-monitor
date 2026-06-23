export function normalizeCreditInteger(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const number = Number(text);
  if (!Number.isFinite(number)) return "";
  return String(Math.max(1, Math.round(number)));
}

export function isValidCreditInteger(value: unknown) {
  return /^[1-9]\d*$/.test(String(value ?? "").trim());
}
