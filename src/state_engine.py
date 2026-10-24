import re


def get_state(user_input: str) -> str:
    text = user_input.lower()
    if re.search(r"\balert\b", text):
        return "Escalate"
    if re.search(r"\b(awaken|rise)\b", text):
        return "Reboot"
    if re.search(r"\b(frustrated|tired)\b", text):
        return "Support"
    if re.search(r"\b(excited|happy)\b", text):
        return "Celebrate"
    if re.search(r"\bhello\b", text):
        return "Engage"
    if re.search(r"\bstatus\b", text):
        return "Report"
    if re.search(r"\b(shutdown|goodbye|exit)\b", text):
        return "Farewell"
    return "LLM"
