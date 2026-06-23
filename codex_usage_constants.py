from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PRICES_PATH = SCRIPT_DIR / "prices.json"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
