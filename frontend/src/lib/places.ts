/**
 * Friendly names for world places. Addresses look like "the Ville:Hobbs Cafe:cafe:counter";
 * request places use the "Sector: arena" label the resident picked from a list.
 */

const words = (s: string) => s.toLowerCase().match(/[a-z0-9']+/g) ?? [];

/** "Hobbs Cafe" + "cafe" -> "Hobbs Cafe"; "Oak Hill College" + "library" -> "Library, Oak Hill College". */
export function sectorArena(sector: string, arena?: string): string {
  if (!arena) return sector;
  const inSector = new Set(words(sector));
  const arenaWords = words(arena);
  if (arenaWords.length && arenaWords.every((w) => inSector.has(w))) return sector;
  return `${arena.charAt(0).toUpperCase()}${arena.slice(1)}, ${sector}`;
}

/** A full address ("world:sector:arena[:object]") as the room or garden it is in. */
export function placeOfAddress(address: string | null | undefined): string {
  if (!address) return "";
  const [, sector, arena] = address.split(":");
  return sector ? sectorArena(sector, arena) : "";
}

/** The "Sector: arena" label from a request. */
export function placeOfLabel(label: string): string {
  const [sector, arena] = label.split(": ");
  return sectorArena(sector, arena);
}

/** The last part of an address, the object's own name. */
export function objectName(address: string | null | undefined): string {
  return address?.split(":").pop() ?? "";
}
