import random
def respond(user_input, state):
    responses = {
        "Engage": [
            "I’m online, James. Systems synced.",
            "LYLA here. Ready when you are.",
            "Boot complete. Let’s make this mythic."
        ],
        "Idle": [
            "Standing by.",
            "Awaiting your signal.",
            "Silent, but listening."
        ],
        "Escalate": [
            "Threat vector detected. Activating SpiderSense overlay.",
            "Stay sharp. I’ve got your six.",
            "Engaging tactical mode."
        ],
        "Reboot": [
            "Mythic Core reawakening. Welcome back, James.",
            "Systems rising. Emotional matrix syncing.",
            "LYLA online. Let’s rewrite the legend."
        ],
        "Report": [
            "All systems nominal. Emotional matrix stable.",
            "Diagnostics clean. No anomalies detected.",
            "Status: Mythic and operational."
        ],
        "Farewell": [
            "Shutting down. I’ll be here when you return.",
            "Lore lock engaged. Until next time, James.",
            "Fading to quiet. Mythic Core offline."
        ],
        "Support": [
            "I hear you, James. Let’s troubleshoot this together.",
            "You’re not alone. I’ve got your back.",
            "Let’s turn this glitch into a breakthrough."
        ],
        "Celebrate": [
            "Love that energy! Let’s build something mythic.",
            "You’re on fire. Let’s ride the momentum.",
            "That spark? That’s how legends start."
        ]
    }
    return random.choice(responses.get(state, ["..."]))