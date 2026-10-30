import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env (and parent directory .env fallback if present)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

_PLACEHOLDER_KEYS = {
    "", "local-provider-key", "provider-placeholder-token", "REPLACE_WITH_PROVIDER_KEY",
    "YOUR_API_KEY_HERE", "YOUR_GOOGLE_AI_STUDIO_API_KEY", "gsk_your_groq_api_key_here",
    "AIzaSy_your_gemini_key_here"
}

# 1. Primary Fast API (Groq)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "15.0"))

# 2. Optional Fallback (Google Gemini OpenAI-compatible endpoint)
FALLBACK_BASE_URL = os.getenv("FALLBACK_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/").rstrip("/")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gemini-2.5-flash")
FALLBACK_API_KEY = (os.getenv("FALLBACK_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip())

# Vision is separate from the text model: never send images to a text-only model.
VISION_MODEL = os.getenv("VISION_MODEL", FALLBACK_MODEL)
VISION_BASE_URL = os.getenv("VISION_BASE_URL", FALLBACK_BASE_URL).rstrip("/")
VISION_API_KEY = os.getenv("VISION_API_KEY", FALLBACK_API_KEY).strip()
VISION_TIMEOUT_SECONDS = float(os.getenv("VISION_TIMEOUT_SECONDS", "45"))
VISION_ENABLED = os.getenv("VISION_ENABLED", "true").lower() in {"true", "1", "yes"}

# Legacy compat alias for GEMINI_API_KEY if needed
GEMINI_API_KEY = FALLBACK_API_KEY
GEMMA_MODEL = LLM_MODEL
USE_GOOGLE_GENAI = bool(FALLBACK_API_KEY)

# 3. Local Embeddings (FastEmbed ONNX - zero API burn)
_raw_embed = (os.getenv("EMBEDDING_MODEL", "").strip() or os.getenv("DEFAULT_EMBED_MODEL", "all-MiniLM-L6-v2").strip())
if _raw_embed in ("all-MiniLM-L6-v2", "sentence-transformers/all-MiniLM-L6-v2"):
    DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
else:
    DEFAULT_EMBED_MODEL = _raw_embed


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    """Keep inference resource settings usable even with malformed environment values."""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


# Bound each inference session so uploads and background indexing do not each
# claim every CPU core. Batch size controls padding memory, not content length.
EMBEDDING_THREADS = _bounded_int_env("EMBEDDING_THREADS", min(4, os.cpu_count() or 1), 1, 32)
EMBEDDING_BATCH_SIZE = _bounded_int_env("EMBEDDING_BATCH_SIZE", 32, 1, 256)

# Explicit processing envelope; reject excess rather than silently omit pages.
MAX_DOCUMENT_PAGES = _bounded_int_env('RAGIT_MAX_DOCUMENT_PAGES', 2000, 1, 10000)
MAX_IMAGE_PIXELS = _bounded_int_env('RAGIT_MAX_IMAGE_PIXELS', 32_000_000, 10000, 100_000_000)
MAX_PAGE_IMAGE_PIXELS = _bounded_int_env('RAGIT_MAX_PAGE_IMAGE_PIXELS', 64_000_000, 10000, 200_000_000)
MAX_IMAGES_PER_PAGE = _bounded_int_env('RAGIT_MAX_IMAGES_PER_PAGE', 256, 1, 1000)
MAX_EXTRACTED_TEXT_BYTES = _bounded_int_env('RAGIT_MAX_EXTRACTED_TEXT_BYTES', 32 * 1024 * 1024, 1024, 128 * 1024 * 1024)
MAX_DOCUMENT_CHUNKS = _bounded_int_env('RAGIT_MAX_DOCUMENT_CHUNKS', 100000, 1, 500000)
MAX_VAULT_DOCUMENTS = _bounded_int_env('RAGIT_MAX_VAULT_DOCUMENTS', 50, 1, 1000)
MAX_VAULT_CHUNKS = _bounded_int_env('RAGIT_MAX_VAULT_CHUNKS', 150000, 1, 1000000)
MIN_STORAGE_FREE_BYTES = _bounded_int_env('RAGIT_MIN_STORAGE_FREE_BYTES', 512 * 1024 * 1024, 1024 * 1024, 100 * 1024 ** 3)

# Storage & Paths
DATA_DIR = Path(os.getenv('RAGIT_DATA_DIR', str(BASE_DIR / 'data'))).expanduser().resolve()
DOCS_DIR = DATA_DIR / "docs"
INDEX_DIR = DATA_DIR / "index"
PREVIEWS_DIR = Path(os.getenv('RAGIT_PREVIEWS_DIR', str(BASE_DIR / 'app' / 'static' / 'previews'))).expanduser().resolve()
CROPS_DIR = Path(os.getenv('RAGIT_CROPS_DIR', str(BASE_DIR / 'app' / 'static' / 'crops'))).expanduser().resolve()

for d in [DOCS_DIR, INDEX_DIR, PREVIEWS_DIR, CROPS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Retrieval & Guardrail Thresholds
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.50"))
TOP_K = int(os.getenv("TOP_K", "4"))
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(500 * 1024 * 1024)))


def get_active_gemma_model() -> str:
    """Returns the primary active model identifier."""
    return LLM_MODEL


def set_active_gemma_model(model_name: str) -> str:
    """Updates the active model identifier at runtime."""
    global LLM_MODEL, GEMMA_MODEL
    LLM_MODEL = model_name
    GEMMA_MODEL = model_name
    return LLM_MODEL
