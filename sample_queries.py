"""Sample query set for testing history review behavior in the Deep Research Agent.

Pattern:
1. Queries 1-3: independent topics
2. Queries 4-6: very similar to 1-3
3. Queries 7-9: somewhat related to 1-3
4. Queries 10-12: independent again
"""

SAMPLE_QUERIES = [
    {
        "id": "q01",
        "domain": "AI",
        "query": "What is the impact of transformer architecture on natural language processing?",
        "expected_match_type": "new",
        "expected_behavior": "Treat as a fresh topic, create a new research plan, and store the published report for future comparisons.",
    },
    {
        "id": "q02",
        "domain": "Physics",
        "query": "What is the role of quantum entanglement in modern physics experiments?",
        "expected_match_type": "new",
        "expected_behavior": "Treat as a fresh topic because it is independent of the AI question.",
    },
    {
        "id": "q03",
        "domain": "Economics",
        "query": "How do interest rate changes affect inflation and consumer spending in an economy?",
        "expected_match_type": "new",
        "expected_behavior": "Treat as a fresh topic because it is independent of the AI and Physics questions.",
    },
    {
        "id": "q04",
        "domain": "AI",
        "query": "How have transformers changed performance in natural language processing tasks?",
        "expected_match_type": "similar",
        "expected_behavior": "Surface the prior AI question and published report, then ask whether to reuse, refresh, or start fresh.",
    },
    {
        "id": "q05",
        "domain": "Physics",
        "query": "How is quantum entanglement used in contemporary physics research?",
        "expected_match_type": "similar",
        "expected_behavior": "Surface the prior Physics question and published report, then ask whether to reuse, refresh, or start fresh.",
    },
    {
        "id": "q06",
        "domain": "Economics",
        "query": "How do rising or falling interest rates influence inflation and household consumption?",
        "expected_match_type": "similar",
        "expected_behavior": "Surface the prior Economics question and published report, then ask whether to reuse, refresh, or start fresh.",
    },
    {
        "id": "q07",
        "domain": "AI",
        "query": "How do large language models handle long-context understanding in text-heavy tasks?",
        "expected_match_type": "related",
        "expected_behavior": "Recognize overlap with the earlier AI question, show related prior work, and propose a plan that extends or refreshes it.",
    },
    {
        "id": "q08",
        "domain": "Physics",
        "query": "How do quantum phenomena influence emerging technologies such as quantum computing?",
        "expected_match_type": "related",
        "expected_behavior": "Recognize overlap with the earlier Physics question, show related prior work, and propose a plan that extends or refreshes it.",
    },
    {
        "id": "q09",
        "domain": "Economics",
        "query": "What monetary policy tools are used to manage inflation and economic growth?",
        "expected_match_type": "related",
        "expected_behavior": "Recognize overlap with the earlier Economics question, show related prior work, and propose a plan that extends or refreshes it.",
    },
    {
        "id": "q10",
        "domain": "Manufacturing",
        "query": "How is computer vision used in manufacturing quality inspection?",
        "expected_match_type": "new",
        "expected_behavior": "Treat as a fresh topic because it should not closely match the earlier AI, Physics, or Economics topics.",
    },
    {
        "id": "q11",
        "domain": "Operations",
        "query": "How can time-series forecasting improve supply chain planning and inventory control?",
        "expected_match_type": "new",
        "expected_behavior": "Treat as a fresh topic because it should not closely match the earlier topics.",
    },
    {
        "id": "q12",
        "domain": "Robotics",
        "query": "What are the most practical use cases of reinforcement learning in robotics?",
        "expected_match_type": "new",
        "expected_behavior": "Treat as a fresh topic because it should not closely match the earlier topics.",
    },
]
