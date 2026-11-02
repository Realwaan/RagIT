"""Model discovery and administrator-only shared model configuration."""
import os
from fastapi import APIRouter, HTTPException
from app import auth, config as cfg
from app.config import get_active_gemma_model, set_active_gemma_model
from app.schemas import ModelSelectRequest
from app.llm import is_llm_configured

router = APIRouter()

def require_model_admin():
    if not auth.enabled():
        return
    admins = {v.strip() for v in os.getenv('RAGIT_ADMIN_USER_IDS', '').split(',') if v.strip()}
    if auth.current_user.get() not in admins:
        raise HTTPException(403, 'Only an administrator can change the shared model.')

@router.get("/api/models")
def list_models():
    """Returns available LLM models, active model selection, and provider status."""
    return {
        "active_model": get_active_gemma_model(),
        "fallback_model": cfg.FALLBACK_MODEL,
        "vision_model": cfg.VISION_MODEL,
        "vision_enabled": cfg.VISION_ENABLED,
        "llm_configured": is_llm_configured(),
        "engine": "Google GenAI (Native)" if cfg.USE_GOOGLE_GENAI else "OpenAI-Compatible",
        "models": cfg.get_available_models(),
    }


@router.post("/api/model/select")
def select_model(payload: ModelSelectRequest):
    """Switch the active LLM model to a supported model identifier."""
    require_model_admin()
    target = payload.model.strip()
    meta = cfg.SUPPORTED_MODELS.get(target)
    if meta is None and target not in {cfg.LLM_MODEL, cfg.FALLBACK_MODEL}:
        allowed = ", ".join(cfg.SUPPORTED_MODELS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model '{target}'. Choose one of: {allowed}.",
        )
    updated = set_active_gemma_model(target)
    info = meta or {"label": f"{updated} (Configured)", "provider": "custom", "tier": "custom"}
    return {
        "ok": True,
        "model": updated,
        "label": info["label"],
        "provider": info["provider"],
        "tier": info["tier"],
    }


@router.post("/api/model/toggle")
def toggle_model():
    """Toggle between high-speed Gemma 4 MoE (26b-a4b-it) and dense Gemma 4 (31b-it)."""
    require_model_admin()
    current = get_active_gemma_model()
    if current == "gemma-4-26b-a4b-it":
        updated = set_active_gemma_model("gemma-4-31b-it")
    else:
        updated = set_active_gemma_model("gemma-4-26b-a4b-it")
    return {
        "ok": True,
        "model": updated,
        "label": "Gemma 4 MoE (~3s)" if updated == "gemma-4-26b-a4b-it" else "Gemma 4 Dense 31B (~28s)"
    }


