// Patterns for <input pattern>, matching what the API accepts (app/phones.py).
// HTML patterns match the whole value and use the `v` regex flag, where "-", "(" and ")"
// must be escaped inside [...]. A pattern the browser can't compile is silently
// ignored, so e2e/public.spec.ts compiles each one with that flag.

/** An Indian mobile (98765 43210, 098765 43210, +91 98765 43210) or any +country number. */
export const MOBILE_PATTERN = String.raw`(\+?91[\s\-]?|0)?[6-9]([\s\-]?[0-9]){9}|\+[1-9]([\s\-]?[0-9]){7,14}`;
export const MOBILE_ERROR = "Enter a 10-digit mobile number, like 98765 43210.";

/** Any phone the business gives, landlines included. */
export const PHONE_PATTERN = String.raw`\+?[0-9\(][0-9\s\-\(\)]{7,18}`;
export const PHONE_ERROR = "Enter a phone number, like 040 2345 6789 or +91 98765 43210.";

/** The browser's verdict on a field, in plain words. */
export function validationMessage(el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement): string {
  const v = el.validity;
  const custom = el.dataset.error;
  if (v.valueMissing) return el instanceof HTMLSelectElement ? "Choose one." : "This is required.";
  if (v.typeMismatch && el.type === "email") return "Enter an email address, like name@example.com.";
  if (v.patternMismatch) return custom ?? "Check the format.";
  if (v.tooShort && "minLength" in el) return `Use at least ${el.minLength} characters.`;
  if (v.tooLong && "maxLength" in el) return `Use at most ${el.maxLength} characters.`;
  if (v.rangeUnderflow && "min" in el) return custom ?? `Enter ${el.min} or more.`;
  if (v.rangeOverflow && "max" in el) return custom ?? `Enter ${el.max} or less.`;
  if (v.badInput) return "Enter a valid value.";
  return custom ?? el.validationMessage;
}
