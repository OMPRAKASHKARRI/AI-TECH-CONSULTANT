
import json

import streamlit as st

from task2_inbox_agent.agent import process_email
from task2_inbox_agent.learning import save_email_review, get_autonomy_status

st.set_page_config(
    page_title="Inbox Agent",
    page_icon="📧",
    layout="wide",
)

st.title("📧 Inbox Agent")
st.caption(
    "AI-powered email classification and reply drafting"
)

st.info(
    "Draft-only mode: generated replies are not sent automatically. "
    "Review every draft before using it."
)

# Keep the current result in the Streamlit session.
if "email_result" not in st.session_state:
    st.session_state.email_result = None

with st.expander("Autonomy eligibility (never auto-sends email)", expanded=False):
    st.caption("A category becomes eligible only after 20 consecutive unedited approvals. Eligibility is informational; this app always requires a human to copy/send drafts.")
    try:
        st.dataframe(get_autonomy_status(), hide_index=True, width="stretch")
    except Exception as error:
        st.caption(f"Autonomy status unavailable until database initialization: {error}")

with st.form("email_form"):
    st.subheader("Customer Email")

    customer_name = st.text_input(
        "Customer name",
        value="Customer",
    )

    subject = st.text_input(
        "Email subject",
        placeholder="Example: Unable to verify my domain",
    )

    body = st.text_area(
        "Email body",
        placeholder="Paste the customer's email here...",
        height=220,
    )

    submitted = st.form_submit_button(
        "Classify Email and Draft Reply",
        type="primary",
    )

if submitted:
    if len(subject.strip()) < 3 or len(body.strip()) < 10:
        st.warning(
            "Enter a subject of at least 3 characters "
            "and an email body of at least 10 characters."
        )
    else:
        with st.spinner(
            "Classifying the email and generating a reply..."
        ):
            try:
                result = process_email(
                    subject=subject.strip(),
                    body=body.strip(),
                    customer_name=customer_name.strip() or "Customer",
                )

                st.session_state.email_result = result

            except Exception as error:
                st.error(f"Could not process the email: {error}")

result = st.session_state.email_result

if result:
    st.divider()
    st.subheader("Classification")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Category", result["category"])

    with col2:
        st.metric("Urgency", result["urgency"])

    with col3:
        st.metric(
            "Human Review",
            "Required" if result["needs_human_review"] else "Recommended check",
        )

    st.markdown("**Issue summary**")
    st.write(result["summary"])

    st.divider()
    st.subheader("Draft Reply")

    edited_draft = st.text_area(
        "Review and edit the reply before using it",
        value=result["draft_reply"],
        height=260,
        key="edited_email_draft",
    )

    st.caption(
        "This application does not send emails. "
        "Copy the reviewed draft into your email client when ready."
    )

    st.download_button(
        "Download Draft",
        data=edited_draft,
        file_name="customer_reply.txt",
        mime="text/plain",
    )

    if result.get("sources"):
        st.subheader("Knowledge Sources")

        for source in result["sources"]:
            title = source.get("title", "Help article")
            url = source.get("url", "")

            if url:
                st.markdown(f"- [{title}]({url})")

    if result["needs_human_review"]:
        st.warning(
            "Please verify the response against the source material "
            "before using it."
        )

    
review_outcome = st.selectbox("Review decision", ["approved", "rejected", "escalated", "reviewed"], index=0)
if st.button("Save Review Decision") and result:
    try:
        review_id = save_email_review(
            subject=result["subject"],
            category=result["category"],
            urgency=result["urgency"],
            original_draft=result["draft_reply"],
            reviewed_draft=edited_draft,
            review_outcome=review_outcome,
        )

        st.session_state["last_reviewed_email"] = {
            "subject": result["subject"],
            "category": result["category"],
            "urgency": result["urgency"],
            "original_draft": result["draft_reply"],
            "reviewed_draft": edited_draft,
            "human_edited": (
                edited_draft.strip()
                != result["draft_reply"].strip()
            ),
            "review_id": review_id,
        }

        st.success(
            f"Review saved successfully. Review ID: {review_id}. Decision: {review_outcome}."
        )
        if review_outcome != "approved":
            st.info("This decision resets the unedited-approval streak for the category.")

        if (
            edited_draft.strip()
            != result["draft_reply"].strip()
        ):
            st.info(
                "Your edits have been recorded for future evaluation."
            )
        else:
            st.info("The original AI draft was saved without changes.")

    except Exception as error:
        st.error(f"Could not save the review: {error}")

