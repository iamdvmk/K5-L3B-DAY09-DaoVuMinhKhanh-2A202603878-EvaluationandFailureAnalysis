"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []

    # 1. Metric values must be real numbers: NaN/inf compare False with every threshold.
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (NaN/inf hides a failing grader)")

    # 2. Graders must not have crashed, and a crash must not hide as a missing value.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), e.g. {pr['evaluator_failures'][0]}")
    rows, brows = pr.get("rows") or [], base.get("rows") or []
    graded = [m["id"] for m in spec.get("metrics", []) if any(m["id"] in r for r in brows + rows)]
    for mid in graded:
        missing = [f"{r.get('item_id')}@{r.get('seed')}" for r in rows if r.get(mid) is None]
        if missing:
            problems.append(f"{len(missing)} row(s) with no value for {mid} (e.g. {missing[0]}): a crashed grader "
                            "drops out of the mean")
        odd = [f"{r.get('item_id')}@{r.get('seed')}={r.get(mid)!r}" for r in rows
               if r.get(mid) is not None and not isinstance(r.get(mid), bool)]
        if odd:
            problems.append(f"{len(odd)} row(s) where {mid} is not a pass/fail bool (e.g. {odd[0]})")

    # 3. Coverage: exactly the baseline's (item, seed) grid, once each.
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}
    for key in ("items", "seeds"):
        if bm.get(key) is not None and pm.get(key) != bm.get(key):
            problems.append(f"manifest {key} {pm.get(key)!r} != baseline {bm.get(key)!r}")
    n_items = bm.get("items", pm.get("items")) or 0
    n_seeds = len(bm.get("seeds", pm.get("seeds")) or [])
    if len(rows) != n_items * n_seeds:
        problems.append(f"{len(rows)} rows, expected {n_items} items x {n_seeds} seeds = {n_items * n_seeds}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item, seed) row(s)")
    pset, bset = set(keys), {(r.get("item_id"), r.get("seed")) for r in brows}
    if brows and pset != bset:
        problems.append(f"(item, seed) set differs from baseline: {len(bset - pset)} missing, {len(pset - bset)} extra")

    # 4. An item keeps its slice tags: relabelling hides a regression from the slice gate.
    btags = {r.get("item_id"): sorted(r.get("slices") or []) for r in brows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in btags and sorted(r.get("slices") or []) != btags[r.get("item_id")]})
    if moved:
        problems.append(f"slice tags changed vs baseline for {len(moved)} item(s), e.g. {moved[0]}")

    # 5. Headline metrics must be what the rows say (no hand-edited or stale aggregates).
    problems += _metrics_match_rows(pr, spec)

    # 6. Ratchet: on the same eval-set version thresholds may only get stricter.
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


_LOOSER = {"max": lambda new, old: new > old, "min": lambda new, old: new < old,
           "max_increase": lambda new, old: new > old}


def _looser(new: dict, old: dict, what: str) -> list[str]:
    out = []
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"ratchet: {what} is no longer blocking")
    nt, ot = new.get("threshold", new), old.get("threshold", old)
    for key, worse in _LOOSER.items():
        if key in ot:
            if key not in nt:
                out.append(f"ratchet: {what} dropped its {key} threshold")
            elif worse(float(nt[key]), float(ot[key])):
                out.append(f"ratchet: {what} {key} {ot[key]} -> {nt[key]} is looser")
    if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
        out.append(f"ratchet: {what} dropped no_significant_drop")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out = []
    new = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        if m["id"] not in new:
            out.append(f"ratchet: metric {m['id']} removed")
        else:
            out += _looser(new[m["id"]], m, f"metric {m['id']}")
    snew = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        key = (s["name"], s["metric"])
        if key not in snew:
            out.append(f"ratchet: slice {key[0]}/{key[1]} removed")
        else:
            out += _looser(snew[key], s, f"slice {key[0]}/{key[1]}")
    for k in ("seeds", "eval_set", "labels"):
        if k in base_spec and spec.get(k) != base_spec.get(k):
            out.append(f"ratchet: {k} changed on the same eval-set version")
    return out


def _metrics_match_rows(pr: dict, spec: dict) -> list[str]:
    from lab9.eval import aggregate

    rows = pr.get("rows") or []
    if not rows:
        return ["report has no rows"]
    ids = [m["id"] for m in spec.get("metrics", []) if all(m["id"] in r for r in rows)]
    if "pass_rate" not in ids and any("pass_rate" in r for r in rows):
        ids.append("pass_rate")
    rows = [dict(r, cost=r.get("cost", 0.0)) for r in rows]
    try:
        again = aggregate(copy.deepcopy(rows), ids, k_values=spec.get("pass_k", []))
    except Exception as exc:                      # rows too broken to aggregate at all
        return [f"cannot recompute metrics from rows: {exc!r}"]
    has_cost = all("cost" in r for r in pr.get("rows") or [])
    out = []
    for k, v in (pr.get("metrics") or {}).items():
        if k == "cost_per_success" and not has_cost:
            continue
        w = again.get(k)
        if isinstance(v, (int, float)) and isinstance(w, (int, float)) and math.isfinite(v):
            if abs(float(v) - float(w)) > 1e-3:
                out.append(f"metric {k}={v} but its rows give {w}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict, note = "fail", "no rows in this slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(th):<30} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
