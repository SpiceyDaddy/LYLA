import unittest

from src.agents import AGENTS, get_agent, route_agent_id


ROUTING_CASES = (
    ("greeting", "Hi, how are you?", "lyla"),
    ("reminder", "Remind me tomorrow to call Mom.", "lyla"),
    ("local time", "What time is it?", "lyla"),
    ("daily planning", "Help me organize my day.", "lyla"),
    ("emotional support", "I'm feeling overwhelmed today.", "lyla"),
    ("memory command", "Remember that I like coffee.", "lyla"),
    ("thanks", "Thanks for helping me with that.", "lyla"),
    ("casual conversation", "I had a long day and want to talk.", "lyla"),
    ("meal planning", "What should I cook for dinner?", "lyla"),
    ("sensitive action", "Delete these old files, please.", "lyla"),
    ("Python repair", "Fix this Python script.", "jarvis"),
    ("traceback", "Debug this traceback and explain the error.", "jarvis"),
    ("JavaScript function", "Write a JavaScript function to sort these names.", "jarvis"),
    ("SQL explanation", "Explain what this SQL query does.", "jarvis"),
    ("class refactor", "Refactor this class to make it easier to read.", "jarvis"),
    ("code bug", "Why does my code have this bug?", "jarvis"),
    ("weather forecast", "What's the weather forecast for Jackson tomorrow?", "friday"),
    ("sales analysis", "Analyze this sales data for trends.", "friday"),
    ("rainfall prediction", "Predict rainfall from these historical numbers.", "friday"),
    ("scenario comparison", "Compare scenarios for next season's crop yields.", "friday"),
    ("probability question", "What is the probability of rolling two sixes?", "friday"),
    ("code security", "Review this login code for security vulnerabilities.", "edith"),
    ("phishing defense", "How do I defend my account from phishing?", "edith"),
    ("permissions audit", "Check these permissions for access-control issues.", "edith"),
    ("malware mitigation", "How can I secure my website against malware?", "edith"),
    ("firewall review", "Review this firewall configuration for security.", "edith"),
    ("plan failure review", "What could go wrong with this plan?", "ultron"),
    ("design assumptions", "Identify the assumptions in this design.", "ultron"),
    ("unclear target", "Could you take a look at this?", "lyla"),
    ("unclear request", "Can you review this for me?", "lyla"),
)


class AgentRoutingTests(unittest.TestCase):
    def test_every_role_has_distinct_personality_and_capability_boundaries(self):
        expected_instructions = {
            "lyla": ("affectionate teasing", "never assume the user's mood"),
            "jarvis": ("quietly witty", "do not have direct file or command access"),
            "friday": ("warm-professional teammate", "cannot browse or fetch live data from chat"),
            "edith": ("film-faithful", "cannot scan systems"),
            "ultron": ("erudite, theatrical skeptic", "failure modes"),
        }

        self.assertEqual(len(AGENTS), len(expected_instructions))
        for agent_id, phrases in expected_instructions.items():
            with self.subTest(agent=agent_id):
                instructions = get_agent(agent_id).instructions.lower()
                for phrase in phrases:
                    self.assertIn(phrase.lower(), instructions)

    def test_labeled_routing_benchmark_meets_90_percent_target(self):
        outcomes = [
            (name, message, expected, route_agent_id(message))
            for name, message, expected in ROUTING_CASES
        ]
        misses = [
            f"{name}: expected {expected}, got {actual} for {message!r}"
            for name, message, expected, actual in outcomes
            if expected != actual
        ]
        correct = sum(
            expected == actual for _name, _message, expected, actual in outcomes
        )
        accuracy = correct / len(ROUTING_CASES)

        self.assertEqual(len(ROUTING_CASES), 30)
        self.assertGreaterEqual(
            accuracy,
            0.9,
            f"Routing accuracy was {accuracy:.0%}; " + "; ".join(misses),
        )

    def test_simple_and_ambiguous_requests_do_not_delegate(self):
        ordinary_cases = [
            (message, expected)
            for _name, message, expected in ROUTING_CASES
            if expected == "lyla"
        ]
        incorrectly_delegated = [
            (message, route_agent_id(message))
            for message, expected in ordinary_cases
            if route_agent_id(message) != expected
        ]

        self.assertGreaterEqual(len(ordinary_cases), 10)
        self.assertEqual(incorrectly_delegated, [])

    def test_everyday_conversation_stays_with_lyla(self):
        self.assertEqual(route_agent_id("Hi, how are you?"), "lyla")
        self.assertEqual(route_agent_id("Remind me tomorrow"), "lyla")
        self.assertEqual(route_agent_id("Delete these files"), "lyla")

    def test_coding_request_routes_to_jarvis(self):
        self.assertEqual(route_agent_id("Fix this Python script"), "jarvis")

    def test_forecast_request_routes_to_friday(self):
        self.assertEqual(
            route_agent_id("What's the forecast for Jackson tomorrow?"),
            "friday",
        )

    def test_security_request_routes_to_edith(self):
        self.assertEqual(
            route_agent_id("Review this login code for security vulnerabilities"),
            "edith",
        )

    def test_risk_review_routes_to_ultron(self):
        self.assertEqual(
            route_agent_id("What could go wrong with this plan?"),
            "ultron",
        )

    def test_unclear_request_stays_with_lyla(self):
        self.assertEqual(route_agent_id("Review this"), "lyla")


if __name__ == "__main__":
    unittest.main()
