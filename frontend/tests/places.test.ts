import { describe, expect, it } from "vitest";
import { objectName, placeOfAddress, placeOfLabel, sectorArena } from "../src/lib/places";

describe("place names", () => {
  it("drops an arena that only repeats the building's name", () => {
    expect(sectorArena("Hobbs Cafe", "cafe")).toBe("Hobbs Cafe");
    expect(placeOfLabel("The Rose and Crown Pub: pub")).toBe("The Rose and Crown Pub");
  });

  it("names the room first otherwise", () => {
    expect(sectorArena("Oak Hill College", "library")).toBe("Library, Oak Hill College");
    expect(placeOfLabel("Dorm for Oak Hill College: Maria Lopez's room")).toBe("Maria Lopez's room, Dorm for Oak Hill College");
  });

  it("reads full addresses", () => {
    expect(placeOfAddress("the Ville:Hobbs Cafe:cafe:counter")).toBe("Hobbs Cafe");
    expect(placeOfAddress("the Ville:Johnson Park")).toBe("Johnson Park");
    expect(placeOfAddress(null)).toBe("");
    expect(objectName("the Ville:Hobbs Cafe:cafe:counter")).toBe("counter");
  });
});
