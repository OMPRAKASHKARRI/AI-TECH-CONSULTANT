

import json
import streamlit as st

from task3_meeting_scope.agents import generate_project_scope
from task3_meeting_scope.scope_diff import compare_scopes
from task3_meeting_scope.approval_store import save_scope_decision, list_scope_decisions, get_latest_approved_scope


st.set_page_config(
    page_title="Meeting to Scope",
    page_icon="📋",
    layout="wide",
)

if "current_scope" not in st.session_state:
    st.session_state.current_scope = None

if "previous_scope" not in st.session_state:
    st.session_state.previous_scope = None
# Scope comparison is anchored to the latest persisted human-approved baseline.
baseline_load_error = None
try:
    st.session_state.previous_scope = get_latest_approved_scope()
except Exception as error:
    st.session_state.previous_scope = None
    baseline_load_error = (
        f"Could not load the approved baseline ({type(error).__name__})."
    )

if "scope_reviewed" not in st.session_state:
    st.session_state.scope_reviewed = False

st.title("📋 Meeting to Scope")
st.caption(
    "Convert meeting transcripts into a draft project scope "
    "with tasks, estimates, assumptions, and risks."
)

st.warning(
    "AI-generated scopes and estimates are preliminary. "
    "A human must review and approve them before they become commitments."
)
if baseline_load_error:
    st.warning(baseline_load_error)

generate_tab, compare_tab = st.tabs(
    ["Generate Scope", "Compare Follow-up"]
)

with generate_tab:
    st.subheader("Meeting Transcript")

    transcript = st.text_area(
        "Paste the meeting transcript",
        placeholder=(
            "Customer: We need an online bookstore website...\n"
            "Consultant: Which features are essential for launch?"
        ),
        height=300,
        key="meeting_transcript",
    )

    if st.button("Generate Project Scope", type="primary"):
        if len(transcript.strip()) < 30:
            st.warning(
                "Please enter a transcript containing at least 30 characters."
            )
        else:
            st.session_state.current_scope = None
            st.session_state.scope_reviewed = False
            with st.spinner("Generating draft project scope..."):
                try:
                    baseline = st.session_state.previous_scope
                    new_scope = generate_project_scope(
                        transcript.strip(),
                        previous_scope=baseline,
                    )

                    # Only a human-approved scope is a valid change-control baseline.
                    st.session_state.previous_scope = baseline
                    st.session_state.current_scope = new_scope
                    st.session_state.scope_reviewed = False

                    st.success("Scope generated successfully.")

                except Exception as error:
                    st.error(f"Scope generation failed: {error}")
                    st.info("No scope was generated. Correct the issue and retry.")

    scope = st.session_state.current_scope

    if scope:
        st.divider()
        st.subheader("Draft Project Scope")

        st.markdown("### Project Summary")
        st.write(scope.get("project_summary", "No summary was generated."))

        st.markdown("### Deliverables")
        deliverables = scope.get("deliverables", [])

        if deliverables:
            for item in deliverables:
                st.markdown(f"- {item}")
        else:
            st.info("No deliverables were returned.")

        st.markdown("### Implementation Tasks")
        tasks = scope.get("tasks", [])

        if tasks:
            task_rows = [
                {
                    "Task": task.get("task", "Unspecified task"),
                    "Description": task.get("description", task.get("rationale", "")),
                    "Low hours": task.get("estimate_low_hours", 0),
                    "Likely hours": task.get("estimate_likely_hours", task.get("estimate_hours", 0)),
                    "High hours": task.get("estimate_high_hours", 0),
                    "Dependencies": ", ".join(task.get("dependencies", [])),
                    "Notes": task.get("notes", ""),
                }
                for task in tasks
            ]

            st.dataframe(
                task_rows,
                width="stretch",
                hide_index=True,
            )

            estimates = scope.get("effort_estimates", {})
            low_total = estimates.get(
                "low_hours",
                sum(float(task.get("estimate_low_hours", 0) or 0) for task in tasks),
            )
            likely_total = estimates.get(
                "likely_hours",
                sum(float(task.get("estimate_likely_hours", task.get("estimate_hours", 0)) or 0) for task in tasks),
            )
            high_total = estimates.get(
                "high_hours",
                sum(float(task.get("estimate_high_hours", 0) or 0) for task in tasks),
            )
            total_low, total_likely, total_high = st.columns(3)
            total_low.metric("Total low estimate", f"{low_total:g} hours")
            total_likely.metric("Total likely estimate", f"{likely_total:g} hours")
            total_high.metric("Total high estimate", f"{high_total:g} hours")
        else:
            st.info("No implementation tasks were returned.")

        for section, title in [
            ("assumptions", "Assumptions"),
            ("exclusions", "Out of Scope"),
            ("risks", "Risks"),
            ("dependencies", "Dependencies"),
            ("open_questions", "Open Questions"),
        ]:
            st.markdown(f"### {title}")
            items = scope.get(section, [])

            if items:
                for item in items:
                    st.markdown(f"- {item}")
            else:
                st.write("None identified.")

        st.markdown("### Product Knowledge Sources")
        sources = scope.get("knowledge_sources", [])

        if sources:
            for source in sources:
                title = source.get("title", "Help article")
                url = source.get("url", "")

                if url:
                    st.markdown(
                        f"- [{title}]({url}) "
                        f"(`{source.get('source_id', url)}`)"
                    )
                    if source.get("snippet"):
                        st.caption(source["snippet"])
                else:
                    st.write(title)
        else:
            if scope.get("knowledge_status") == "unavailable":
                st.warning(
                    "Task 1 was unavailable, so product capabilities could not "
                    "be checked. Start the Knowledge Brain API and retry."
                )
            elif scope.get("knowledge_status") == "malformed_response":
                st.warning(
                    "Task 1 returned an invalid response. Verify product "
                    "capabilities manually before approval."
                )
            else:
                st.info(
                    "Task 1 returned no supporting sources. Check that its "
                    "knowledge base has been synchronized."
                )
        if scope.get("knowledge_error"):
            st.caption(scope["knowledge_error"])

        if scope.get("knowledge_review_required", True):
            st.warning(
                "Product knowledge needs human verification before approval."
            )

        review_status = scope.get("review_status", "draft")
        if scope.get("approval_required", True):
            st.warning(f"Review status: {review_status} — human approval required.")
        else:
            st.success(f"Review status: {review_status}.")

        st.download_button(
            "Download Scope JSON",
            data=json.dumps(scope, indent=2, ensure_ascii=False),
            file_name="project_scope.json",
            mime="application/json",
        )

        reviewer = st.text_input(
            "Reviewer identifier",
            value="",
            placeholder="Enter your reviewer name or ID",
        )
        decision = st.selectbox("Human scope decision", ["needs_changes", "approved", "rejected"], key="scope_decision")
        if st.button("Save Human Decision"):
            try:
                approval_id = save_scope_decision(scope, decision, reviewer)
                scope["review_status"] = decision
                scope["approval_required"] = decision != "approved"
                st.session_state.scope_reviewed = decision == "approved"
                st.success(f"Decision saved persistently (record #{approval_id}): {decision}.")
                if decision != "approved":
                    st.warning("This scope must not be sent to the client as an approved proposal.")
                else:
                    st.session_state.previous_scope = scope
            except Exception as error:
                st.error(f"Could not save approval decision: {error}")

        with st.expander("Recent scope decisions"):
            try:
                st.dataframe(list_scope_decisions(), hide_index=True, width="stretch")
            except Exception as error:
                st.caption(f"Decision history unavailable: {error}")
    else:
        st.info("No generated scope draft is available. Submit a transcript to generate one.")

with compare_tab:
    st.subheader("Compare a Follow-up Meeting")

    previous_scope = st.session_state.previous_scope
    current_scope = st.session_state.current_scope

    if previous_scope is None or current_scope is None:
        st.info(
            "A comparison requires a generated scope and a previously "
            "approved baseline. Drafts and scopes marked needs_changes "
            "are not baselines."
        )
    else:
        st.write("**Previous scope:**")
        st.write(previous_scope.get("project_summary", "Summary unavailable"))

        st.write("**Updated scope:**")
        st.write(current_scope.get("project_summary", "Summary unavailable"))

        if st.button("Compare Scopes", type="primary"):
            try:
                diff = compare_scopes(previous_scope, current_scope)

                st.markdown("### Scope Change Summary")
                st.json(diff)

                st.metric(
                    "Previous estimated hours",
                    diff["previous_estimated_hours"],
                )
                st.metric(
                    "Updated estimated hours",
                    diff["updated_estimated_hours"],
                )
                st.metric(
                    "Estimate change (hours)",
                    diff["estimate_change_hours"],
                )

                if diff["possible_scope_change"]:
                    st.warning(
                        "Potential scope changes detected. "
                        "Human approval is required."
                    )
                else:
                    st.success("No scope changes detected by the comparison.")

            except Exception as error:
                st.error(f"Comparison failed: {error}")

st.divider()
st.caption("Task 3 — Meeting to Scope | Drafts require human approval")
