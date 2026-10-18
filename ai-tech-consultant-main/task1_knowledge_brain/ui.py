
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"
TIMEOUT = 180

st.set_page_config(
    page_title="AI Tech Consultant",
    page_icon="🧠",
    layout="wide",
)

if "messages" not in st.session_state:
    st.session_state.messages = []


def api_request(method, path, **kwargs):
    """Send a request to the FastAPI backend."""
    response = requests.request(
        method,
        f"{API_URL}{path}",
        timeout=TIMEOUT,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def show_sources(sources):
    if not sources:
        st.info("No supporting article sources were returned.")
        return

    with st.expander("📚 View sources"):
        for source in sources:
            title = source.get("title", "Help article")
            url = source.get("url", "")

            if url:
                st.markdown(f"- [{title}]({url})")
            else:
                st.write(title)


st.title("🧠 AI Tech Consultant")
st.caption("Knowledge Brain · Brilliant Directories Support")

try:
    health = requests.get(f"{API_URL}/health", timeout=5)
    if health.ok:
        st.success("Backend connected")
    else:
        st.warning("Backend returned an unexpected status.")
except requests.RequestException:
    st.error(
        "Cannot connect to FastAPI. Start your backend in another "
        "terminal before using these features."
    )

chat_tab, sync_tab, review_tab = st.tabs(
    ["💬 Chat Assistant", "🔄 Article Sync", "🧑‍💼 Expert Review"]
)

with chat_tab:
    st.subheader("Ask the Knowledge Brain")
    st.write(
        "Ask questions about Brilliant Directories. "
        "Answers should be grounded in indexed knowledge."
    )

    if st.button("➕ New conversation"):
        st.session_state.messages = []
        st.rerun()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message["role"] == "assistant":
                show_sources(message.get("sources", []))

                if message.get("needs_human_help", False):
                    st.warning("Human review recommended.")

    question = st.chat_input(
        "Ask a support question...",
        key="knowledge_chat_input",
    )

    if question:
        history = [
            {
                "role": item["role"],
                "content": item["content"],
            }
            for item in st.session_state.messages
            if item["role"] in {"user", "assistant"}
        ]

        st.session_state.messages.append(
            {"role": "user", "content": question}
        )

        with st.spinner("Searching the knowledge base..."):
            try:
                result = api_request(
                    "POST",
                    "/knowledge/ask",
                    json={
                        "question": question,
                        "history": history,
                    },
                )

                answer = result.get(
                    "answer",
                    "No answer was returned.",
                )
                sources = result.get("sources", [])
                needs_help = result.get(
                    "needs_human_help",
                    False,
                )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "sources": sources,
                        "needs_human_help": needs_help,
                    }
                )

                st.rerun()

            except requests.RequestException as error:
                st.error(f"Could not get an answer: {error}")

with sync_tab:
    st.subheader("Synchronize Help Articles")
    st.write(
        "Crawl the configured support sitemap and save discovered "
        "articles to the local knowledge database."
    )

    max_pages = st.number_input(
        "Maximum pages to crawl",
        min_value=1,
        max_value=500,
        value=20,
        step=5,
    )

    delay_seconds = st.number_input(
        "Delay between requests (seconds)",
        min_value=0.0,
        max_value=10.0,
        value=1.0,
        step=0.5,
    )

    st.caption(
        "A larger crawl may take longer. Follow the website's "
        "access rules and crawling limits."
    )

    if st.button("Start Article Sync", type="primary"):
        with st.spinner("Crawling and indexing articles..."):
            try:
                result = api_request(
                    "POST",
                    "/knowledge/sync",
                    json={
                        "max_pages": int(max_pages),
                        "delay_seconds": float(delay_seconds),
                    },
                )

                st.success("Sync request completed.")
                st.json(result)

            except requests.RequestException as error:
                st.error(f"Article sync failed: {error}")

with review_tab:
    st.subheader("Submit Expert Knowledge")
    st.write(
        "Human experts can submit verified answers. New answers "
        "remain pending until reviewed."
    )

    with st.form("expert_feedback_form"):
        expert_question = st.text_area(
            "Customer question",
            placeholder="Enter the customer's question...",
        )

        expert_answer = st.text_area(
            "Verified expert answer",
            placeholder="Enter the approved product guidance...",
        )

        submitted = st.form_submit_button("Submit for Review")

    if submitted:
        if len(expert_question.strip()) < 3:
            st.warning("Enter a question with at least 3 characters.")
        elif len(expert_answer.strip()) < 3:
            st.warning("Enter an answer with at least 3 characters.")
        else:
            try:
                result = api_request(
                    "POST",
                    "/knowledge/feedback",
                    json={
                        "question": expert_question.strip(),
                        "expert_answer": expert_answer.strip(),
                    },
                )

                st.success("Expert answer submitted for review.")
                st.json(result)

            except requests.RequestException as error:
                st.error(f"Could not submit feedback: {error}")

    st.divider()
    st.subheader("Pending Expert Reviews")

    if st.button("Refresh Pending Reviews"):
        st.session_state["refresh_reviews"] = True

    try:
        pending = api_request(
            "GET",
            "/knowledge/feedback",
        )

        if not pending:
            st.info("No pending expert answers.")
        else:
            for item in pending:
                feedback_id = item.get("id")
                question_text = item.get("question", "")
                answer_text = item.get("expert_answer", "")

                with st.expander(
                    f"Review #{feedback_id}: {question_text[:70]}"
                ):
                    st.markdown("**Customer question**")
                    st.write(question_text)

                    st.markdown("**Proposed expert answer**")
                    st.write(answer_text)

                    col1, col2 = st.columns(2)

                    with col1:
                        if st.button(
                            "Approve",
                            key=f"approve_{feedback_id}",
                        ):
                            try:
                                api_request(
                                    "PATCH",
                                    f"/knowledge/feedback/{feedback_id}",
                                    params={"status": "approved"},
                                )
                                st.success("Feedback approved.")
                                st.rerun()
                            except requests.RequestException as error:
                                st.error(f"Approval failed: {error}")

                    with col2:
                        if st.button(
                            "Reject",
                            key=f"reject_{feedback_id}",
                        ):
                            try:
                                api_request(
                                    "PATCH",
                                    f"/knowledge/feedback/{feedback_id}",
                                    params={"status": "rejected"},
                                )
                                st.success("Feedback rejected.")
                                st.rerun()
                            except requests.RequestException as error:
                                st.error(f"Rejection failed: {error}")

    except requests.RequestException as error:
        st.error(f"Could not load pending reviews: {error}")

st.divider()
st.caption(
    "Task 1 — Knowledge Brain | "
    "Source-grounded answers | Human review"
)

