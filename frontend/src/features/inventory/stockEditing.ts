// Keep decimal input as text until the backend validates/stores Decimal values.
export function stockEditValue(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}
export function validatedStockValue(value: unknown, integer = false): string | number | null {
  const text = stockEditValue(value).trim().replace(/,/g, '');
  if (!text) return null;
  const pattern = integer ? /^\d+$/ : /^(?:\d+(?:\.\d{1,4})?|\.\d{1,4})$/;
  if (!pattern.test(text)) throw new Error(integer
    ? 'Lead time must be a nonnegative whole number of days.'
    : 'Enter a nonnegative number with at most four decimal places. Clear a cell to leave it unspecified.');
  if (integer && (!Number.isSafeInteger(Number(text)) || Number(text) > 2147483647))
    throw new Error('Lead time is too large.');
  return integer ? Number(text) : text;
}

export function validatedStockText(value: unknown): string | null {
  const text = stockEditValue(value).trim();
  if (text.length > 2000) throw new Error('Description must contain at most 2000 characters.');
  return text || null;
}
