
import re
from difflib import SequenceMatcher


# Explicit aliases prevent common wording variations from
# being incorrectly reported as scope changes.
ALIASES = {
    "backend development": "backend",
    "back-end development": "backend",
    "back end development": "backend",
    "frontend development": "frontend",
    "front-end development": "frontend",
    "front end development": "frontend",
    "database setup": "database",
    "email notification system": "email notifications",
    "user account management": "customer accounts",
    "customer account management": "customer accounts",
    "user authentication": "authentication",
    "customer login": "login",
    "log in": "login",
    "website design": "website design",
}


def normalize_text(value: str) -> str:
    text = str(value).strip().casefold()
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return ALIASES.get(text, text)


def compare_items(old_items: list, new_items: list) -> tuple:
    """Compare items after applying explicit wording aliases."""

    old_map = {}
    new_map = {}

    for item in old_items:
        text = str(item).strip()
        key = normalize_text(text)
        if key:
            old_map.setdefault(key, text)

    for item in new_items:
        text = str(item).strip()
        key = normalize_text(text)
        if key:
            new_map.setdefault(key, text)

    added = [
        new_map[key]
        for key in sorted(new_map.keys() - old_map.keys())
    ]
    removed = [
        old_map[key]
        for key in sorted(old_map.keys() - new_map.keys())
    ]

    return added, removed


def _item_changes(old_items: list, new_items: list) -> tuple[list, list, list]:
    added, removed = compare_items(old_items, new_items)
    modifications = []
    remaining_added = list(added)
    remaining_removed = list(removed)

    candidates = sorted(
        (
            SequenceMatcher(
                None,
                normalize_text(old).split(),
                normalize_text(new).split(),
            ).ratio(),
            old,
            new,
        )
        for old in removed
        for new in added
    )
    for similarity, old, new in reversed(candidates):
        if similarity < 0.55 or old not in remaining_removed or new not in remaining_added:
            continue
        modifications.append({"previous": old, "updated": new})
        remaining_removed.remove(old)
        remaining_added.remove(new)

    return remaining_added, remaining_removed, modifications


def _matches_exclusion(item: str, exclusion: str) -> bool:
    item_tokens = set(normalize_text(item).split())
    exclusion_tokens = set(normalize_text(exclusion).split())
    if not item_tokens or not exclusion_tokens:
        return False
    shared = len(item_tokens & exclusion_tokens)
    return shared / min(len(item_tokens), len(exclusion_tokens)) >= 0.6


def compare_scopes(
    previous_scope: dict | None,
    updated_scope: dict,
) -> dict:
    """Compare two project scopes and identify changes."""

    if previous_scope is None:
        updated_hours = _calculate_hours(updated_scope)
        return {
            "comparison_available": False,
            "comparison_note": "No explicitly approved baseline is available.",
            "added_requirements": [],
            "removed_requirements": [],
            "modified_requirements": [],
            "added_deliverables": [],
            "removed_deliverables": [],
            "modified_deliverables": [],
            "potentially_out_of_scope": [],
            "baseline_exclusion_conflicts": [],
            "affected_baseline_requirements": [],
            "unchanged_baseline_requirements": [],
            "previous_estimated_hours": None,
            "updated_estimated_hours": updated_hours,
            "estimate_change_hours": None,
            "possible_scope_change": False,
            "approval_required": True,
        }

    old_analysis = previous_scope.get("meeting_analysis", {})
    new_analysis = updated_scope.get("meeting_analysis", {})

    added, removed, modified = _item_changes(
        old_analysis.get("requirements", []),
        new_analysis.get("requirements", []),
    )

    added_deliverables, removed_deliverables, modified_deliverables = _item_changes(
        previous_scope.get("deliverables", []),
        updated_scope.get("deliverables", []),
    )

    new_or_modified = (
        added
        + [change["updated"] for change in modified]
        + added_deliverables
        + [change["updated"] for change in modified_deliverables]
    )
    previous_exclusions = previous_scope.get("exclusions", [])
    exclusion_conflicts = [
        {"item": item, "baseline_exclusion": exclusion}
        for item in new_or_modified
        for exclusion in previous_exclusions
        if _matches_exclusion(item, exclusion)
    ]
    old_hours = _calculate_hours(previous_scope)
    new_hours = _calculate_hours(updated_scope)

    return {
        "comparison_available": True,
        "comparison_note": "Compared with the latest explicitly approved scope.",
        "added_requirements": added,
        "removed_requirements": removed,
        "modified_requirements": modified,
        "added_deliverables": added_deliverables,
        "removed_deliverables": removed_deliverables,
        "modified_deliverables": modified_deliverables,
        "potentially_out_of_scope": new_or_modified,
        "baseline_exclusion_conflicts": exclusion_conflicts,
        "affected_baseline_requirements": (
            removed + [change["previous"] for change in modified]
        ),
        "unchanged_baseline_requirements": [
            item
            for item in old_analysis.get("requirements", [])
            if normalize_text(item)
            in {
                normalize_text(value)
                for value in new_analysis.get("requirements", [])
            }
        ],
        "previous_estimated_hours": old_hours,
        "updated_estimated_hours": new_hours,
        "estimate_change_hours": new_hours - old_hours,
        "possible_scope_change": bool(
            added
            or removed
            or modified
            or added_deliverables
            or removed_deliverables
            or modified_deliverables
        ),
        "approval_required": True,
    }


def _calculate_hours(scope: dict) -> float:
    total = 0.0
    for task in scope.get("tasks", []):
        try:
            total += float(
                task.get("estimate_likely_hours", task.get("estimate_hours", 0))
                or 0
            )
        except (TypeError, ValueError):
            pass
    return total
