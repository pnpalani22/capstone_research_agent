from langgraph.types import Command

from graph import build_app


def main():
    app = build_app()
    config = {"configurable": {"thread_id": "alice-research-demo"}}

    print("Starting research run...")
    app.invoke(
        {
            "question": "What is the impact of transformer architecture on NLP?",
            "user_id": "alice",
            "max_iterations": 3,
            "messages": [],
        },
        config=config,
    )

    state = app.get_state(config)
    if state.tasks and state.tasks[0].interrupts:
        payload = state.tasks[0].interrupts[0].value
        print("\nDraft awaiting review:\n")
        print(payload)

        print("\nResuming with approval...\n")
        final_state = app.invoke(Command(resume="approved"), config=config)
        print(final_state.get("final_report", "No final report available."))
    else:
        print("No interrupt was raised. Review the graph configuration.")


if __name__ == "__main__":
    main()
