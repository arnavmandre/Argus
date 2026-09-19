#!/usr/bin/env python3
"""
Validate a .usda file.

  pip install usd-core            # optional but recommended: enables the real check
  python validate_usd.py out/city.usda

With `pxr` installed it opens the file with the actual OpenUSD library and lists prims.
Without it, it runs structural checks (braces, prim names, sibling-name clashes).
Passing the structural check is NOT proof Omniverse will open it - the pxr check is.
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "out/city.usda"

try:
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(path)
    prims = list(stage.Traverse())
    kinds = {}
    for p in prims:
        kinds[p.GetTypeName()] = kinds.get(p.GetTypeName(), 0) + 1
    print(f"[pxr] opened OK: {len(prims)} prims, upAxis={UsdGeom.GetStageUpAxis(stage)}, "
          f"metersPerUnit={UsdGeom.GetStageMetersPerUnit(stage)}")
    print("[pxr] prim types:", kinds)
    paths = [p for p in prims if p.GetName().startswith("e_")]
    for p in paths[:3]:
        print("[pxr] sample path attrs:", p.GetPath(), p.GetAttribute("urbantwin:shade_pct").Get())
    sys.exit(0)
except ImportError:
    print("[info] pxr not installed - running structural checks only (pip install usd-core for the real check)")

text = open(path, encoding="utf-8").read()
errors = []

if not text.startswith("#usda 1.0"):
    errors.append("missing '#usda 1.0' header")
if text.count("{") != text.count("}"):
    errors.append(f"unbalanced braces: {text.count('{')} '{{' vs {text.count('}')} '}}'")
if text.count("(") != text.count(")"):
    errors.append("unbalanced parentheses")

ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
stack, seen, n_prims = [], {}, 0
for lineno, line in enumerate(text.splitlines(), 1):
    m = re.match(r'^\s*def\s+(\w+)\s+"([^"]*)"', line)
    if m:
        n_prims += 1
        name = m.group(2)
        if not ident.match(name):
            errors.append(f"line {lineno}: invalid prim name {name!r}")
        parent = tuple(stack)
        key = (parent, name)
        if key in seen:
            errors.append(f"line {lineno}: duplicate sibling prim name {name!r}")
        seen[key] = lineno
        stack.append(name)
        pending_open = True
        continue
    s = line.strip()
    if s == "}" and stack:
        stack.pop()

print(f"[structural] {n_prims} prims found")
if errors:
    print("[structural] PROBLEMS:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("[structural] no problems found")
