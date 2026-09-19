/**
 * The six citizen behaviours and their fixed display colours.
 *
 * The linear RGB triples are copied verbatim from `BEHAVIOR_STYLE` in
 * `phase9/agents_instancer.py`, which is what Omniverse renders. Hex is derived
 * from the triples rather than typed by hand so the web legend cannot drift
 * away from the viewport.
 */
import type { CitizenBehavior } from "./types";

export const BEHAVIORS: readonly CitizenBehavior[] = [
  "CONTINUE",
  "STRESSED",
  "SEEK_SHADE",
  "SEEK_SHELTER",
  "REROUTE",
  "AVOID_AREA",
] as const;

const BEHAVIOR_RGB: Record<CitizenBehavior, readonly [number, number, number]> = {
  CONTINUE: [0.2, 0.85, 0.3],
  STRESSED: [1.0, 0.55, 0.08],
  SEEK_SHADE: [0.95, 0.88, 0.12],
  SEEK_SHELTER: [0.1, 0.75, 0.95],
  REROUTE: [0.65, 0.25, 0.9],
  AVOID_AREA: [0.95, 0.12, 0.12],
};

function toHex(rgb: readonly [number, number, number]): string {
  return (
    "#" +
    rgb
      .map((c) => Math.round(Math.min(1, Math.max(0, c)) * 255).toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase()
  );
}

export interface BehaviorMeta {
  id: CitizenBehavior;
  /** Colour name as documented in the handoff. */
  colorName: string;
  hex: string;
  rgb: readonly [number, number, number];
  label: string;
  meaning: string;
}

export const BEHAVIOR_META: Record<CitizenBehavior, BehaviorMeta> = {
  CONTINUE: {
    id: "CONTINUE",
    colorName: "green",
    hex: toHex(BEHAVIOR_RGB.CONTINUE),
    rgb: BEHAVIOR_RGB.CONTINUE,
    label: "Continue",
    meaning: "Walks the chosen route without changing plan.",
  },
  STRESSED: {
    id: "STRESSED",
    colorName: "orange",
    hex: toHex(BEHAVIOR_RGB.STRESSED),
    rgb: BEHAVIOR_RGB.STRESSED,
    label: "Stressed",
    meaning: "Completes the trip but under sustained discomfort.",
  },
  SEEK_SHADE: {
    id: "SEEK_SHADE",
    colorName: "yellow",
    hex: toHex(BEHAVIOR_RGB.SEEK_SHADE),
    rgb: BEHAVIOR_RGB.SEEK_SHADE,
    label: "Seek shade",
    meaning: "Prefers shaded segments because of heat exposure.",
  },
  SEEK_SHELTER: {
    id: "SEEK_SHELTER",
    colorName: "cyan",
    hex: toHex(BEHAVIOR_RGB.SEEK_SHELTER),
    rgb: BEHAVIOR_RGB.SEEK_SHELTER,
    label: "Seek shelter",
    meaning: "Breaks the trip to get out of rain or cold.",
  },
  REROUTE: {
    id: "REROUTE",
    colorName: "purple",
    hex: toHex(BEHAVIOR_RGB.REROUTE),
    rgb: BEHAVIOR_RGB.REROUTE,
    label: "Reroute",
    meaning: "Takes a different route than the lowest-distance one.",
  },
  AVOID_AREA: {
    id: "AVOID_AREA",
    colorName: "red",
    hex: toHex(BEHAVIOR_RGB.AVOID_AREA),
    rgb: BEHAVIOR_RGB.AVOID_AREA,
    label: "Avoid area",
    meaning: "Abandons the area rather than crossing it.",
  },
};

/** Behaviours that read as a problem, used only for wording, never for colour. */
export const ADVERSE_BEHAVIORS: readonly CitizenBehavior[] = [
  "STRESSED",
  "SEEK_SHADE",
  "SEEK_SHELTER",
  "REROUTE",
  "AVOID_AREA",
];
