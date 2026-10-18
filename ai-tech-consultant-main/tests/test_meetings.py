
import pytest

from task3_meeting_scope.scope_diff import (
    normalize_text,
    compare_items,
    compare_scopes,
)
from task3_meeting_scope import approval_store
from task3_meeting_scope.agents import extract_json


def test_normalize_text_ignores_case_and_extra_spaces():
    assert normalize_text("  BACKEND   DEVELOPMENT ") == "backend"


def test_normalize_text_handles_known_aliases():
    assert normalize_text("Frontend Development") == "frontend"
    assert normalize_text("Back-end development") == "backend"


def test_compare_items_detects_added_and_removed_items():
    added, removed = compare_items(
        ["Backend", "Email Notifications"],
        ["Backend", "Shopping Cart"],
    )

    assert added == ["Shopping Cart"]
    assert removed == ["Email Notifications"]


def test_compare_items_ignores_duplicate_items():
    added, removed = compare_items(
        ["Backend", "Backend"],
        ["Backend"],
    )

    assert added == []
    assert removed == []


def test_compare_scopes_detects_scope_changes():
    previous = {
        "meeting_analysis": {
            "requirements": ["Backend", "Email Notifications"]
        },
        "deliverables": ["Admin Dashboard"],
        "tasks": [{"estimate_hours": 10}],
    }

    updated = {
        "meeting_analysis": {
            "requirements": ["Backend", "Shopping Cart"]
        },
        "deliverables": ["Customer Dashboard"],
        "tasks": [{"estimate_hours": 15}],
    }

    result = compare_scopes(previous, updated)

    assert result["added_requirements"] == ["Shopping Cart"]
    assert result["removed_requirements"] == ["Email Notifications"]
    assert result["added_deliverables"] == ["Customer Dashboard"]
    assert result["removed_deliverables"] == ["Admin Dashboard"]
    assert result["previous_estimated_hours"] == 10
    assert result["updated_estimated_hours"] == 15
    assert result["estimate_change_hours"] == 5
    assert result["possible_scope_change"] is True
    assert result["approval_required"] is True


def test_compare_scopes_accepts_equivalent_wording():
    previous = {
        "meeting_analysis": {
            "requirements": ["Backend Development"]
        },
        "deliverables": [],
        "tasks": [{"estimate_hours": 20}],
    }

    updated = {
        "meeting_analysis": {
            "requirements": ["Backend"]
        },
        "deliverables": [],
        "tasks": [{"estimate_hours": 25}],
    }

    result = compare_scopes(previous, updated)

    assert result["added_requirements"] == []
    assert result["removed_requirements"] == []
    assert result["possible_scope_change"] is False
    assert result["estimate_change_hours"] == 5
    assert result["approval_required"] is True


def test_compare_scopes_handles_invalid_estimates():
    previous = {
        "meeting_analysis": {"requirements": []},
        "deliverables": [],
        "tasks": [
            {"estimate_hours": "invalid"},
            {"estimate_hours": 5},
        ],
    }

    updated = {
        "meeting_analysis": {"requirements": []},
        "deliverables": [],
        "tasks": [{"estimate_hours": 8}],
    }

    result = compare_scopes(previous, updated)

    assert result["previous_estimated_hours"] == 5
    assert result["updated_estimated_hours"] == 8
    assert result["estimate_change_hours"] == 3


def test_follow_up_comparison_flags_new_features_and_baseline_exclusions():
    baseline = {
        "project_summary": "Bookstore",
        "meeting_analysis": {
            "requirements": [
                "Responsive bookstore website",
                "Book browsing and search",
                "Customer registration and login",
                "Order email notifications",
            ]
        },
        "deliverables": ["Responsive storefront", "Book catalog"],
        "exclusions": ["Native mobile application", "Online payments"],
        "tasks": [{"estimate_likely_hours": 80}],
    }
    updated = {
        "meeting_analysis": {
            "requirements": [
                "Responsive bookstore website",
                "Book browsing and search",
                "Customer registration and login",
                "Order email notifications",
                "Native mobile application",
                "Loyalty points program",
                "Automated courier integration",
            ]
        },
        "deliverables": [
            "Responsive storefront",
            "Book catalog",
            "Native mobile app",
            "Loyalty program",
            "Courier integration",
        ],
        "tasks": [{"estimate_likely_hours": 120}],
        "review_status": "draft",
        "approval_required": True,
    }

    result = compare_scopes(baseline, updated)

    assert result["comparison_available"] is True
    assert {
        "Native mobile application",
        "Loyalty points program",
        "Automated courier integration",
    } <= set(result["added_requirements"])
    assert result["potentially_out_of_scope"]
    assert any(
        "mobile" in conflict["item"].lower()
        for conflict in result["baseline_exclusion_conflicts"]
    )
    assert result["approval_required"] is True
    assert result["possible_scope_change"] is True


def test_scope_comparison_marks_requirement_rewording_as_modification():
    baseline = {
        "meeting_analysis": {"requirements": ["Search books by title or author"]},
        "deliverables": [],
        "tasks": [],
    }
    updated = {
        "meeting_analysis": {
            "requirements": ["Search books by title, author, and genre"]
        },
        "deliverables": [],
        "tasks": [],
    }

    result = compare_scopes(baseline, updated)

    assert result["modified_requirements"] == [
        {
            "previous": "Search books by title or author",
            "updated": "Search books by title, author, and genre",
        }
    ]
    assert result["affected_baseline_requirements"] == [
        "Search books by title or author"
    ]


def test_scope_comparison_without_approved_baseline_is_unavailable():
    result = compare_scopes(None, {"tasks": [{"estimate_hours": 10}]})

    assert result["comparison_available"] is False
    assert "approved baseline" in result["comparison_note"]
    assert result["previous_estimated_hours"] is None
    assert result["approval_required"] is True


def test_approved_scope_history_drives_follow_up_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_store, "DB_PATH", str(tmp_path / "scopes.sqlite3"))
    initial = {
        "project_summary": "Bookstore",
        "meeting_analysis": {
            "requirements": [
                "Responsive bookstore website",
                "Book browsing and search",
                "Order notifications",
            ]
        },
        "deliverables": ["Responsive storefront", "Book catalog"],
        "exclusions": ["Native mobile application"],
        "tasks": [{"estimate_low_hours": 40, "estimate_likely_hours": 60, "estimate_high_hours": 90}],
        "approval_required": True,
    }
    approval_store.save_scope_decision(initial, "needs_changes", "reviewer-1")
    assert approval_store.get_latest_approved_scope() is None
    approval_store.save_scope_decision(initial, "approved", "reviewer-2")
    approved_baseline = approval_store.get_latest_approved_scope()

    follow_up = {
        "meeting_analysis": {
            "requirements": [
                "Responsive bookstore website",
                "Book browsing and search",
                "Order notifications",
                "Native mobile application",
                "Loyalty points program",
                "Automated courier integration",
            ]
        },
        "deliverables": [
            "Responsive storefront",
            "Book catalog",
            "Mobile application",
            "Loyalty program",
            "Courier integration",
        ],
        "tasks": [{"estimate_low_hours": 80, "estimate_likely_hours": 120, "estimate_high_hours": 180}],
        "review_status": "draft",
        "approval_required": True,
    }

    comparison = compare_scopes(approved_baseline, follow_up)

    assert comparison["comparison_available"] is True
    assert set(comparison["added_requirements"]) == {
        "Native mobile application",
        "Loyalty points program",
        "Automated courier integration",
    }
    assert any(
        conflict["baseline_exclusion"] == "Native mobile application"
        and "mobile" in conflict["item"].lower()
        for conflict in comparison["baseline_exclusion_conflicts"]
    )
    assert comparison["unchanged_baseline_requirements"] == [
        "Responsive bookstore website",
        "Book browsing and search",
        "Order notifications",
    ]
    assert comparison["approval_required"] is True
    assert follow_up["approval_required"] is True


def test_extract_json_parses_plain_json():
    result = extract_json('{"requirements": ["Login"], "approval_required": true}')

    assert result["requirements"] == ["Login"]
    assert result["approval_required"] is True


def test_extract_json_parses_markdown_fenced_json():
    result = extract_json(
        '```json\n{"project_summary": "Website"}\n```'
    )

    assert result["project_summary"] == "Website"


def test_extract_json_finds_json_inside_text():
    result = extract_json(
        'Result follows: {"project_summary": "Store"} complete.'
    )

    assert result["project_summary"] == "Store"


def test_extract_json_rejects_invalid_input():
    with pytest.raises(ValueError):
        extract_json("This is not JSON")


def test_extract_json_rejects_empty_input():
    with pytest.raises(ValueError):
        extract_json("")
