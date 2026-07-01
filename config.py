# =============================================================================
# config.py - Thinkster Elevate Automation Configuration
# =============================================================================

EMAIL    = "dvignesh4991_old@gmail.com"
PASSWORD = "Apple@123"

# ---------------------------------------------------------------------------
# Browser Settings
# ---------------------------------------------------------------------------
HEADLESS          = False
WINDOW_MAXIMIZE   = True
PAGE_LOAD_TIMEOUT = 60
IMPLICIT_WAIT     = 0

# ---------------------------------------------------------------------------
# Application URLs
# ---------------------------------------------------------------------------
BASE_URL  = "https://elevate.hellothinkster.com/"
LOGIN_URL = "https://elevate.hellothinkster.com/login"

# ---------------------------------------------------------------------------
# Wait Timeouts (seconds)
# ---------------------------------------------------------------------------
SHORT_WAIT   = 5
DEFAULT_WAIT = 15
LONG_WAIT    = 30

# Delays for question changing and rendering (seconds)
QUESTION_TRANSITION_DELAY = 1.5
QUESTION_SETTLE_DELAY     = 0.5

# ---------------------------------------------------------------------------
# Student to Select
# ---------------------------------------------------------------------------
TARGET_STUDENT = "Thomas D"

# ---------------------------------------------------------------------------
# Index File
# ---------------------------------------------------------------------------
INDEX_FILE = "worksheet_index.json"
ANSWERS_FILE = "worksheet_answers.json"


# ---------------------------------------------------------------------------
# Screenshots / Artifact Directory
# ---------------------------------------------------------------------------
SCREENSHOTS_DIR = "C:/Users/ELCOT/.gemini/antigravity-ide/brain/a1009690-e737-4b28-826b-cdfcee5e8dbc"


# ---------------------------------------------------------------------------
# Session Cache Settings
# ---------------------------------------------------------------------------
# If True, Chrome will use a persistent profile in the workspace directory.
# This avoids logging in and selecting the student profile on every run.
PERSIST_SESSION = True
CHROME_PROFILE_DIR = "chrome_profile"


# ---------------------------------------------------------------------------
# Retry Settings
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
RETRY_DELAY = 2

# ---------------------------------------------------------------------------
# AI / LLM Settings
# ---------------------------------------------------------------------------
# AI_PROVIDER choices:
#   "zhipu"      - Zhipu AI (BigModel.cn)
#   "groq"       - Free cloud API. Get key at: https://console.groq.com
#   "ollama"     - Local Ollama (no key needed). Run: ollama serve && ollama pull llama3
#   "openrouter" - Many free models. Get key at: https://openrouter.ai
#   "mistral"    - Mistral AI cloud. Get key at: https://console.mistral.ai

AI_PROVIDER = "ollama"

# Zhipu AI / BigModel Key:
AI_API_KEY = ""

# Model name for the chosen provider:
#   zhipu:      "glm-4-flash"  or  "glm-4"
#   groq:       "llama-3.3-70b-versatile"  or  "llama3-8b-8192"
#   ollama:     "llama3"  or  "mistral"  or  "phi3"  or  "gpt-oss:120b"
#   openrouter: "meta-llama/llama-3-8b-instruct:free"
#   mistral:    "mistral-large-latest"
AI_MODEL = "gpt-oss:120b"

AI_TIMEOUT = 60  # seconds per AI call

# ---------------------------------------------------------------------------
# Ollama Settings (for local or Cloud Ollama setups)
# ---------------------------------------------------------------------------
# Base URL for Ollama API:
#   Local default: "http://localhost:11434"
#   Cloud / Custom default: e.g. "https://ollama.com" or "https://ollama.com/api/generate"
OLLAMA_BASE_URL = "https://ollama.com/api/generate"
OLLAMA_API_KEY  = "7f1b819e47464844b7052601677ecb8e.k0oueSkr5PRznaG6skQk9TnC"

# ---------------------------------------------------------------------------
# Math Expert System Prompt
# ---------------------------------------------------------------------------
MATH_EXPERT_PROMPT = (
    "act as a mathematics expert and perform a complete review.\n\n"
    "For each question image :\n"
    "- Verify whether the question is mathematically correct.\n"
    "- Solve the question and identify the correct answer.\n"
    "- Check whether the answer key (if visible) is correct.\n"
    "- Check whether more than one option can be considered correct.\n"
    "- Identify confusing, ambiguous, misleading, or poorly worded questions.\n"
    "- Check whether students may get confused between two or more options.\n"
    "- Verify that all options are distinct and that only one answer can reasonably "
    "be selected (unless the question explicitly allows multiple answers).\n"
    "- Check whether the expected answer format is clearly specified "
    "(ordered pair, fraction, interval notation, etc.).\n"
    "- Check for UI issues visible in the screenshot "
    "(hidden keypad, mobile-view issues, unclear labels, missing instructions, overlapping content, etc.).\n\n"
    "If there is any issue, provide it in exactly this format:\n"
    "Issue: <clear one-line description of the issue>\n\n"
    "Examples:\n"
    "Issue: The worksheet marks the correct slope of the chord as 1/3, but the mathematically correct answer is -2/3; therefore, the answer key is incorrect.\n"
    "Issue: Both Option A and Option D have eccentricity 5/3, resulting in multiple correct answers in a single-select question.\n"
    "Issue: The question does not specify the expected answer format; providing a hint to enter the focus as an ordered pair using parentheses, such as (x, y), would help avoid student confusion.\n"
    "Issue: The keypad is not displayed for this question, making it difficult for students to enter their answer.\n\n"
    "If NO issue exists, respond exactly in this format:\n"
    "Check: Question and options are mathematically correct; the correct answer is <answer>. "
    "The answer is unique, and no logical, ambiguity, multiple-answer, answer-key, or UI issues were found.\n\n"
    "For True/False questions, provide the correct sequence (e.g., T, F, T, T) and report any answer-key mistakes.\n"
    "Always double-check calculations before giving the final response."
)

# ---------------------------------------------------------------------------
# MongoDB Settings
# ---------------------------------------------------------------------------
# MongoDB connection URI (shared with the analysis component)
MONGO_URI = "mongodb+srv://admin:admin123@cluster0.eu3cz1g.mongodb.net/?appName=Cluster0"
MONGO_DB = "Thinkster_testing"
MONGO_ANSWERS_COLLECTION = "WS_answers"
