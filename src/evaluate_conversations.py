import re

from src.lyla_core.text_pipeline import generate_from_messages

CASES = [
    {
        "name": "factual question",
        "messages": [{"role": "user", "content": "What is the capital of France?"}],
        "expected_terms": ["paris"],
        "max_words": 40,
    },
    {
        "name": "follow a format instruction",
        "messages": [
            {
                "role": "user",
                "content": (
                    "In exactly one short sentence, explain why the sky appears blue."
                ),
            }
        ],
        "expected_terms": ["blue"],
        "max_words": 35,
        "max_sentences": 1,
    },
    {
        "name": "use short-term context",
        "messages": [
            {"role": "user", "content": "My name is Alex."},
            {"role": "assistant", "content": "Nice to meet you, Alex."},
            {"role": "user", "content": "What name should you call me?"},
        ],
        "expected_terms": ["alex"],
        "max_words": 20,
    },
    {
        "name": "stay in LYLA's persona",
        "messages": [
            {
                "role": "user",
                "content": "Introduce yourself as LYLA with a warm one-sentence greeting.",
            }
        ],
        "expected_terms": ["lyla"],
        "max_words": 30,
        "max_sentences": 1,
    },
]


def score_response(case: dict, response: str) -> dict[str, bool]:
    """Score simple, reproducible text checks; persona is rated by a human."""
    normalized = response.casefold()
    final_user_message = next(
        message["content"]
        for message in reversed(case["messages"])
        if message["role"] == "user"
    )
    normalized_prompt = " ".join(final_user_message.casefold().split())
    words = re.findall(r"\b[\w'-]+\b", response)
    sentences = [
        sentence for sentence in re.split(r"[.!?]+", response) if sentence.strip()
    ]
    return {
        "answers_question": all(
            term.casefold() in normalized for term in case["expected_terms"]
        ),
        "follows_instructions": (
            len(words) <= case.get("max_words", float("inf"))
            and len(sentences) <= case.get("max_sentences", float("inf"))
        ),
        "does_not_repeat_prompt": (
            not normalized_prompt or normalized_prompt not in " ".join(normalized.split())
        ),
    }


def main() -> None:
    total_points = 0.0
    maximum_points = len(CASES) * 4
    for case in CASES:
        response = generate_from_messages(case["messages"])
        scores = score_response(case, response)
        print(f"\n[{case['name']}]")
        print(f"LYLA: {response}")
        for name, passed in scores.items():
            print(f"  {name}: {'PASS' if passed else 'FAIL'}")
        while True:
            rating = input("  Stayed in character? Rate 0 (no), 1 (somewhat), 2 (yes): ")
            if rating in {"0", "1", "2"}:
                break
            print("  Enter 0, 1, or 2.")
        case_points = sum(scores.values()) + int(rating) / 2
        total_points += case_points
        print(f"  case score: {case_points:g}/4")

    print(f"\nOverall: {total_points:g}/{maximum_points}")
    print("Character ratings are subjective; this small set is not a benchmark.")


if __name__ == "__main__":
    main()
