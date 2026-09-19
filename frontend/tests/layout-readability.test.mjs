import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const viewer = readFileSync(
  new URL("../components/OmniverseViewer.tsx", import.meta.url),
  "utf8",
);
const dashboard = readFileSync(
  new URL("../components/Dashboard.tsx", import.meta.url),
  "utf8",
);
const scenarioControls = readFileSync(
  new URL("../components/ScenarioControls.tsx", import.meta.url),
  "utf8",
);
const styles = readFileSync(
  new URL("../app/globals.css", import.meta.url),
  "utf8",
);

test("offline viewport stays compact instead of becoming a large empty panel", () => {
  assert.match(
    viewer,
    /min-h-\[260px\] sm:min-h-\[300px\] lg:min-h-\[340px\]/,
  );
});

test("viewport loading placeholder uses the same compact height", () => {
  assert.match(
    dashboard,
    /min-h-\[260px\] sm:min-h-\[300px\] lg:min-h-\[340px\]/,
  );
  assert.doesNotMatch(dashboard, /min-h-\[460px\]/);
});

test("run status does not create an empty column beneath headline metrics", () => {
  assert.match(
    dashboard,
    /<div className="mt-5 xl:mt-6">\s*<RunStatus/,
  );
});

test("wide screens scan scenario fields in two compact columns", () => {
  assert.match(scenarioControls, /2xl:grid-cols-2/);
  assert.match(scenarioControls, /2xl:space-y-0/);
});

test("analysis cards flow in independent columns without stretched empty panels", () => {
  const columns =
    dashboard.match(/className="contents xl:flex xl:flex-col xl:gap-6"/g) ?? [];

  assert.equal(columns.length, 2);
  for (const order of [1, 2, 3, 4]) {
    assert.match(dashboard, new RegExp(`className="order-${order}"`));
  }
});

test("dark mode uses a lifted canvas rather than a pure black page gap", () => {
  const darkTheme = styles.match(
    /@media \(prefers-color-scheme: dark\) \{([\s\S]*?)\n\}/,
  )?.[1];

  assert.ok(darkTheme, "dark theme token block should exist");
  assert.doesNotMatch(darkTheme, /--canvas:\s*#000000/);
});
