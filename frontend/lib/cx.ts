/** Minimal class joiner. Keeps a clsx dependency out of the bundle. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
