import { BookOpen, Confetti, MoonStars, Smiley } from "@phosphor-icons/react";
import { describe, expect, it } from "vitest";
import { activityIcon, activityLabel, iconByName } from "../src/lib/icons";
import { addMinutes, hourOf, isBefore, minutesBetween } from "../src/lib/time";

describe("sim time", () => {
  it("treats naive ISO times as the town's own clock", () => {
    expect(hourOf("2023-02-13T17:30:00")).toBe(17.5);
    expect(minutesBetween("2023-02-13T23:50:00", "2023-02-14T00:10:00")).toBe(20);
    expect(addMinutes("2023-02-13T23:50:00", 15)).toBe("2023-02-14T00:05:00");
    expect(isBefore("2023-02-13T08:00:00", "2023-02-13T08:00:10")).toBe(true);
    expect(isBefore("2023-02-13T08:00:10", "2023-02-13T08:00:10")).toBe(false);
  });
});

describe("activity icons and labels", () => {
  it("matches the activity text", () => {
    expect(activityIcon("sleeping")).toBe(MoonStars);
    expect(activityIcon("decorate Hobbs Cafe for the Valentine's Day party")).toBe(Confetti);
    expect(activityIcon("read a book at the library")).toBe(BookOpen);
    expect(activityIcon("")).toBe(Smiley);
  });

  it("strips the paper's progress suffixes", () => {
    expect(activityLabel("have lunch at Hobbs Cafe (getting started)")).toBe("Have lunch at Hobbs Cafe");
    expect(activityLabel("")).toBe("Idle");
  });

  it("falls back for unknown config icon names", () => {
    expect(iconByName("BookOpen")).toBe(BookOpen);
    expect(iconByName("NoSuchIcon")).not.toBeUndefined();
  });
});
