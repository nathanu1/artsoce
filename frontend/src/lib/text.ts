import { ApiError } from "../apiError";

/** Server reasons are lowercase clauses ("needs 1 more Bloom motif"); show them as sentences. */
export function sentence(text: string): string {
  const t = text.trim();
  if (!t) return t;
  const first = t.charAt(0).toUpperCase() + t.slice(1);
  return /[.!?…]$/.test(first) ? first : `${first}.`;
}

const SERVER_HINT = "Check that “ga play” is still running, then try again.";

/**
 * Toast copy for a failed request: a rule the town refused is explained as is; anything else
 * (no connection, a server error) says what to do next.
 */
export function failureBody(e: unknown): string {
  if (e instanceof ApiError && e.status >= 400 && e.status < 500) return sentence(e.message);
  if (e instanceof ApiError && e.status === 0) return `The town server is not answering. ${SERVER_HINT}`;
  const msg = e instanceof Error ? e.message : String(e);
  return msg ? `${sentence(msg)} ${SERVER_HINT}` : SERVER_HINT;
}

const lists = new Intl.ListFormat(undefined, { style: "long", type: "conjunction" });
/** "Isabella, Maria and Klaus" in the reader's language. */
export const listOf = (names: string[]) => lists.format(names);

/** The platform's shortcut modifier, for labels ("⌘" on Apple devices, "Ctrl" elsewhere). */
export const MOD = typeof navigator !== "undefined" && /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent) ? "⌘" : "Ctrl";

/** "1 piece", "3 pieces". */
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
