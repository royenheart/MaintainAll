#!/usr/bin/env python3
"""Offline, dependency-free policy lookup. Never calls a provider or switches models."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "registry.json"


def validate(data: dict) -> None:
    """Check policy invariants and references; v1 deliberately has no calibrated rows."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(data["schema_version"] == 1, "unsupported schema_version")
    date.fromisoformat(data["updated_at"])
    tiers, profiles = data["tiers"], data["profiles"]
    require(data["policy"]["unknown_tier"] == "U", "unknown tier must be U")
    require(isinstance(data["policy"]["max_age_days"], int)
            and data["policy"]["max_age_days"] > 0, "max_age_days must be positive")
    require({k: v["rank"] for k, v in tiers.items()} ==
            {"U": 0, "T1": 1, "T2": 2, "T3": 3}, "invalid tier order")
    for name, tier in tiers.items():
        require(tier["profile"] in profiles, f"unknown profile for {name}")
    for profile in profiles.values():
        require(bool(profile["instructions"]), "empty profile")
        for supplement in profile["supplements"]:
            require(supplement in data["supplements"], "unknown supplement")
        for skill in profile["additional_skills"]:
            require(skill in data["skills"], "unknown additional skill")
    require("contract-check" in data["supplements"] and
            "risk-review" in data["supplements"], "missing fallback supplements")
    for skill, spec in data["skills"].items():
        require(spec["task"] in data["tasks"], f"unknown task for {skill}")
        require(spec["minimum_tier"] in tiers, f"unknown minimum tier for {skill}")
    for source in data["sources"].values():
        require(source["url"].startswith("https://"), "source must have HTTPS URL")
        date.fromisoformat(source["accessed_at"])
    for task in data["tasks"].values():
        require(all(s in data["sources"] for s in task["sources"]), "unknown task source")
    for model, row in data["models"].items():
        size = row["size"]
        require(all(v is None or (isinstance(v, (int, float)) and v > 0)
                    for v in (size["total_b"], size["active_b"])), "invalid model size")
        if size["total_b"] is not None and size["active_b"] is not None:
            require(size["active_b"] <= size["total_b"], "active size exceeds total")
        if size["total_b"] is not None or size["active_b"] is not None:
            require(size["source"] in data["sources"], "size requires a source")
        require(bool(row["variants"]), f"no variants for {model}")
        for variant, record in row["variants"].items():
            require(record["status"] in {"provisional", "unassessed"},
                    "v1 accepts only provisional/unassessed tiers; calibration requires a reviewed schema change")
            require(set(record["task_tiers"]) == set(data["tasks"]), "incomplete task coverage")
            require(all(t in tiers for t in record["task_tiers"].values()), "unknown task tier")
            if record["status"] == "unassessed":
                require(set(record["task_tiers"].values()) == {"U"},
                        "unassessed records must use U for every task")
            require(bool(record["rationale"]), "missing tier rationale")
            require(bool(record["evidence"]) and
                    all(s in data["sources"] for s in record["evidence"]), "invalid evidence")
            date.fromisoformat(record["reviewed_at"])
            require(isinstance(record["config"], dict), "invalid configuration")
            require(record["local_runs"] == [], "v1 cannot certify local runs")
            require(record["community_observations"] == [], "v1 cannot certify community observations")
    for observation in data["observations"]:
        model = data["models"][observation["model"]]
        require(observation["variant"] in model["variants"], "unknown observation variant")
        require(observation["source"] in data["sources"], "unknown observation source")
        require(observation["direction"] in {"higher", "lower"}, "invalid metric direction")
        require(isinstance(observation["value"], (int, float)), "invalid metric value")
        require(bool(observation["benchmark_version"]) and bool(observation["limitations"]),
                "observation needs version and limitations")
        date.fromisoformat(observation["observed_at"])
        if observation.get("measured_at") is not None:
            date.fromisoformat(observation["measured_at"])


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    validate(data)
    return data


def resolve(data: dict, model: str | None, variant: str | None, skill: str,
            task: str | None = None, risk: str = "normal", as_of: date | None = None) -> dict:
    validate(data)
    if skill not in data["skills"]:
        raise ValueError(f"unknown skill: {skill}")
    task = task or data["skills"][skill]["task"]
    if task not in data["tasks"] or risk not in {"normal", "high"}:
        raise ValueError("unknown task or risk")
    today = as_of or date.today()
    row = data["models"].get(model)
    record = row["variants"].get(variant) if row else None
    tier = "U"
    reason = "unknown_model" if row is None else "unknown_configuration"
    if record:
        age = (today - date.fromisoformat(record["reviewed_at"])).days
        source_ages = [(today - date.fromisoformat(data["sources"][s]["accessed_at"])).days
                       for s in record["evidence"]]
        observation_ages = [
            (today - date.fromisoformat(o[key])).days
            for o in data["observations"]
            if o["model"] == model and o["variant"] == variant and o["source"] in record["evidence"]
            for key in ("observed_at", "measured_at") if o.get(key) is not None
        ]
        ages = [age] + source_ages + observation_ages
        if any(a < 0 for a in ages):
            reason = "future_evidence"
        elif max(ages) > data["policy"]["max_age_days"]:
            reason = "stale_evidence"
        else:
            tier = record["task_tiers"][task]
            reason = "unassessed" if tier == "U" else record["status"]
    profile_name = data["tiers"][tier]["profile"]
    profile = data["profiles"][profile_name]
    supplement_ids = list(profile["supplements"])
    if reason != "calibrated":
        supplement_ids.append("contract-check")
    if risk == "high":
        supplement_ids.append("risk-review")
    supplement_ids = list(dict.fromkeys(supplement_ids))
    required = data["skills"][skill]["minimum_tier"]
    gap = data["tiers"][tier]["rank"] < data["tiers"][required]["rank"]
    return {
        "schema_version": data["schema_version"], "as_of": today.isoformat(),
        "model": model, "variant": variant, "skill": skill, "task": task,
        "tier": tier, "status": reason, "profile": profile_name,
        "instructions": profile["instructions"],
        "supplements": {k: data["supplements"][k] for k in supplement_ids},
        "additional_skills": [s for s in profile["additional_skills"] if s != skill],
        "minimum_tier": required, "capability_gap": gap,
        "next_action": "decompose_or_request_supported_escalation" if gap else "proceed_with_checks",
        "needs_calibration": True,
        "evidence": record["evidence"] if record else [],
        "rationale": record["rationale"] if record else "No exact model/configuration evidence.",
        "model_notes": row["notes"] if row else [],
        "automatic_model_switch": False,
    }


def check_install(root: Path) -> dict:
    """Check a filesystem bundle's adaptation dependencies by frontmatter name."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"skills root is not a directory: {root}")
    catalog = {}
    for path in sorted(root.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        front = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|$)", text, re.DOTALL)
        name_line = re.search(r"^name:[ \t]*(.+?)[ \t]*$", front[1], re.MULTILINE) if front else None
        if not name_line:
            raise ValueError(f"missing single-line frontmatter name: {path}")
        name = name_line[1].strip("\"'")
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError(f"invalid skill name: {path}")
        if name in catalog:
            raise ValueError(f"ambiguous skill name {name}: {catalog[name]} and {path}")
        catalog[name] = path.resolve(strict=True)
    if "model-policy" not in catalog:
        raise ValueError("missing model-policy skill; install its complete directory")
    policy_dir = catalog["model-policy"].parent
    for relative in ("registry.json", "methodology.md", "scripts/resolve.py"):
        if not (policy_dir / relative).is_file():
            raise ValueError(f"missing policy resource: {policy_dir / relative}")
    data = load_registry(policy_dir / "registry.json")
    selected = sorted(set(catalog) & set(data["skills"]))
    required = sorted({s for p in data["profiles"].values() for s in p["additional_skills"]}) if selected else []
    missing = sorted(set(required) - set(catalog))
    if missing:
        raise ValueError(f"missing model-adaptation supporting skills: {', '.join(missing)}")
    return {"valid": True, "skills_root": str(root),
            "policy_skill": str(catalog["model-policy"]),
            "registry": str(policy_dir / "registry.json"),
            "development_skills": selected, "required_support": required}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--check-install", type=Path, metavar="SKILLS_ROOT",
                      help="Check a filesystem bundle; locate skills by frontmatter name")
    parser.add_argument("--model")
    parser.add_argument("--variant", help="Exact configuration key; omission stays unknown")
    parser.add_argument("--skill")
    parser.add_argument("--task", help="Optional domain override, e.g. review for a reviewer")
    parser.add_argument("--risk", choices=("normal", "high"), default="normal")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Replay a policy snapshot date")
    args = parser.parse_args()
    try:
        if args.check_install is not None:
            if args.registry != DEFAULT_REGISTRY:
                parser.error("--check-install uses the installed policy's registry; omit --registry")
            print(json.dumps(check_install(args.check_install), ensure_ascii=False, indent=2))
            return 0
        data = load_registry(args.registry)
        if args.validate:
            print(json.dumps({"valid": True, "models": len(data["models"]),
                              "skills": len(data["skills"])}))
        else:
            if not args.skill:
                parser.error("--skill is required unless --validate is used")
            print(json.dumps(resolve(data, args.model, args.variant, args.skill,
                                     args.task, args.risk, args.as_of), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"Policy error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
