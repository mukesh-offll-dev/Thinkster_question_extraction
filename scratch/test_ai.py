import requests

OLLAMA_API_KEY = "7f1b819e47464844b7052601677ecb8e.k0oueSkr5PRznaG6skQk9TnC"

headers = {
    "Authorization": f"Bearer {OLLAMA_API_KEY}",
    "Content-Type": "application/json",
}

MATH_EXPERT_PROMPT = (
    "You are a Mathematics Professor. Solve the following question. Double-check your calculations.\n"
    "Important: Your response must consist ONLY of the final answer. No reasoning, no explanation, no markdown.\n"
    "Formatting instructions:\n"
    "- If the question is Multiple Choice:\n"
    "  Provide the exact text of the correct option (e.g. '3.5') or if options are lettered, the letter (e.g., 'A').\n"
    "- If the question is True/False:\n"
    "  Respond with exactly 'True' or 'False'.\n"
    "- If the question requires typing/keypad input (fraction, numeric, decimal, coordinates, math expression):\n"
    "  Provide the exact characters to enter (e.g., '24', '-3', '3/4', '(2,3)', '0.5').\n"
    "  For fractions, use a slash (e.g. '3/4').\n"
    "  For coordinates, use standard parentheses (e.g. '(x, y)').\n"
    "  Do not include units unless explicitly asked as part of the input text.\n"
    "  Only output the final answer string."
)

user_message = (
    "Question:\n"
    "If one solution of a quadratic equation with real coefficients is\n"
    "x\n"
    "=\n"
    "3\n"
    "−\n"
    "5\n"
    "i\n"
    ", find the product of the two solutions."
)

prompt_text = f"System: {MATH_EXPERT_PROMPT}\n\nUser: {user_message}"

payload = {
    "model": "gpt-oss:120b",
    "prompt": prompt_text,
    "stream": False,
    "options": {"temperature": 0.1}
}

print("Sending request to cloud Ollama with newline-separated math question...")
try:
    response = requests.post(
        "https://ollama.com/api/generate",
        headers=headers,
        json=payload,
        timeout=30
    )
    print("Status Code:", response.status_code)
    print("Raw Response:", response.text)
except Exception as exc:
    print("Error:", exc)
