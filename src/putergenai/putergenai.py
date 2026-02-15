import asyncio
import json
import logging
import socket
import ssl
from datetime import datetime, timedelta
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

import aiohttp
import certifi
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

__version__ = "3.5.0"

KV_MAX_KEY_SIZE: Optional[int] = None
KV_MAX_VALUE_SIZE: Optional[int] = None


class NonEmptyStr(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    value: str = Field(..., min_length=1)


class PathStr(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    value: str = Field(..., min_length=1, pattern=r"^[\w\-\.\~\/ \(\)]+$")


def validate_string(s: str) -> str:
    """Validate non-empty string (strip whitespace)."""
    return NonEmptyStr.model_validate({"value": s}).value


def validate_path(p: str) -> str:
    """Validate path string (non-empty, alphanumeric/.-/)."""
    return PathStr.model_validate({"value": p}).value


class UrlStr(BaseModel):
    value: HttpUrl


def validate_url(u: str) -> str:
    """Validate HTTP/HTTPS URL."""
    return UrlStr.model_validate({"value": u}).value


class PuterClient:
    """
    Asynchronous Client for the Puter.com API.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        ignore_ssl: bool = False,
        auto_update_models: bool = False,
    ):
        self.token = token
        self.ignore_ssl = ignore_ssl
        self.auto_update_models = auto_update_models
        self.api_base = "https://api.puter.com"
        self.login_url = "https://puter.com/login"
        self._session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Origin": "https://puter.com",
            "Referer": "https://puter.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        }

        # Model to driver mapping
        self.model_to_driver = {
            # OpenAI GPT-5.1 models
            "gpt-5.1": "openai-completion",
            "gpt-5.1-codex": "openai-completion",
            "gpt-5.1-codex-mini": "openai-completion",
            "gpt-5.1-chat-latest": "openai-completion",
            # OpenAI GPT-5 models
            "gpt-5-2025-08-07": "openai-completion",
            "gpt-5": "openai-completion",
            "gpt-5-mini-2025-08-07": "openai-completion",
            "gpt-5-mini": "openai-completion",
            "gpt-5-nano-2025-08-07": "openai-completion",
            "gpt-5-nano": "openai-completion",
            "gpt-5-chat-latest": "openai-completion",
            # OpenAI GPT-4o models
            "gpt-4o": "openai-completion",
            "gpt-4o-mini": "openai-completion",
            # OpenAI o-series models
            "o1": "openai-completion",
            "o1-mini": "openai-completion",
            "o1-pro": "openai-completion",
            "o3": "openai-completion",
            "o3-mini": "openai-completion",
            "o4-mini": "openai-completion",
            # OpenAI GPT-4.1 models
            "gpt-4.1": "openai-completion",
            "gpt-4.1-mini": "openai-completion",
            "gpt-4.1-nano": "openai-completion",
            # OpenAI GPT-4.5 models
            "gpt-4.5-preview": "openai-completion",
            # Claude models
            "claude-opus-4-5": "claude",
            "claude-opus-4-5-latest": "claude",
            "claude-opus-4.5": "claude",
            "claude-haiku-4-5-20251001": "claude",
            "claude-haiku-4.5": "claude",
            "claude-haiku-4-5": "claude",
            "claude-sonnet-4-5-20250929": "claude",
            "claude-sonnet-4.5": "claude",
            "claude-sonnet-4-5": "claude",
            "claude-opus-4-1-20250805": "claude",
            "claude-opus-4-1": "claude",
            "claude-opus-4-20250514": "claude",
            "claude-opus-4": "claude",
            "claude-opus-4-latest": "claude",
            "claude-sonnet-4-20250514": "claude",
            "claude-sonnet-4": "claude",
            "claude-sonnet-4-latest": "claude",
            "claude-3-7-sonnet-20250219": "claude",
            "claude-3-7-sonnet-latest": "claude",
            "claude-3-5-sonnet-20241022": "claude",
            "claude-3-5-sonnet-latest": "claude",
            "claude-3-5-sonnet-20240620": "claude",
            "claude-3-haiku-20240307": "claude",
            # Mistral models
            "mistral-large-latest": "mistral",
            "mistral-medium-2508": "mistral",
            "mistral-medium-latest": "mistral",
            "mistral-medium": "mistral",
            "ministral-3b-2410": "mistral",
            "ministral-3b-latest": "mistral",
            "ministral-8b-2410": "mistral",
            "ministral-8b-latest": "mistral",
            "open-mistral-7b": "mistral",
            "mistral-tiny": "mistral",
            "mistral-tiny-2312": "mistral",
            "open-mistral-nemo": "mistral",
            "open-mistral-nemo-2407": "mistral",
            "mistral-tiny-2407": "mistral",
            "mistral-tiny-latest": "mistral",
            "pixtral-large-2411": "mistral",
            "pixtral-large-latest": "mistral",
            "mistral-large-pixtral-2411": "mistral",
            "codestral-2508": "mistral",
            "codestral-latest": "mistral",
            "devstral-small-2507": "mistral",
            "devstral-small-latest": "mistral",
            "pixtral-12b-2409": "mistral",
            "pixtral-12b": "mistral",
            "pixtral-12b-latest": "mistral",
            "mistral-small-2506": "mistral",
            "mistral-small-latest": "mistral",
            "magistral-medium-2509": "mistral",
            "magistral-medium-latest": "mistral",
            "magistral-small-2509": "mistral",
            "magistral-small-latest": "mistral",
            "mistral-moderation-2411": "mistral",
            "mistral-moderation-latest": "mistral",
            "mistral-ocr-2505": "mistral",
            "mistral-ocr-latest": "mistral",
            # xAI/Grok models
            "grok-beta": "xai",
            "grok-vision-beta": "xai",
            "grok-3": "xai",
            "grok-3-fast": "xai",
            "grok-3-mini": "xai",
            "grok-3-mini-fast": "xai",
            "grok-2-vision": "xai",
            "grok-2": "xai",
            # DeepSeek models
            "deepseek-chat": "deepseek",
            "deepseek-reasoner": "deepseek",
            "deepseek/deepseek-v3.2": "deepseek",
            "deepseek/deepseek-v3.2-speciale": "deepseek",
            # MiniMax models
            "minimax/minimax-m2.1": "minimax",
            "minimax/minimax-m2-her": "minimax",
            "minimax/minimax-m2": "minimax",
            "minimax/minimax-m1": "minimax",
            "minimax/minimax-01": "minimax",
            # Google Gemini models
            "gemini-1.5-flash": "google",
            "gemini-2.0-flash": "google",
            "gemini-2.0-flash-lite": "google",
            "gemini-2.5-flash": "google",
            "gemini-2.5-flash-lite": "google",
            "gemini-2.5-pro": "google",
            "gemini-3-pro-preview": "google",
            # TogetherAI models (using together-ai driver)
            "togetherai:togethercomputer/Refuel-Llm-V2": "together-ai",
            "togetherai:cartesia/sonic": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": "together-ai",
            "togetherai:cartesia/sonic-2": "together-ai",
            "togetherai:meta-llama/LlamaGuard-7b": "together-ai",
            "togetherai:togethercomputer/MoA-1": "together-ai",
            "togetherai:meta-llama/LlamaGuard-2-8b": "together-ai",
            "togetherai:meta-llama/Llama-3.3-70B-Instruct-Turbo": "together-ai",
            "togetherai:Qwen/Qwen2.5-72B-Instruct-Turbo": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-dev": "together-ai",
            "togetherai:Alibaba-NLP/gte-modernbert-base": "together-ai",
            "togetherai:mistralai/Mistral-Small-24B-Instruct-2501": "together-ai",
            "togetherai:marin-community/marin-8b-instruct": "together-ai",
            "togetherai:kwaivgI/kling-1.6-standard": "together-ai",
            "togetherai:meta-llama/Meta-Llama-Guard-3-11B-Vision-Turbo": "together-ai",
            "togetherai:black-forest-labs/FLUX.2-flex": "together-ai",
            "togetherai:meta-llama/Meta-Llama-Guard-3-8B": "together-ai",
            "togetherai:deepseek-ai/DeepSeek-R1": "together-ai",
            "togetherai:Qwen/Qwen3-Next-80B-A3B-Thinking": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-dev-lora": "together-ai",
            "togetherai:HiDream-ai/HiDream-I1-Full": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-krea-dev": "together-ai",
            "togetherai:togethercomputer/MoA-1-Turbo": "together-ai",
            "togetherai:Lykon/DreamShaper": "together-ai",
            "togetherai:HiDream-ai/HiDream-I1-Dev": "together-ai",
            "togetherai:Qwen/Qwen-Image": "together-ai",
            "togetherai:RunDiffusion/Juggernaut-pro-flux": "together-ai",
            "togetherai:google/imagen-4.0-preview": "together-ai",
            "togetherai:google/imagen-4.0-ultra": "together-ai",
            "togetherai:google/veo-3.0": "together-ai",
            "togetherai:minimax/hailuo-02": "together-ai",
            "togetherai:stabilityai/stable-diffusion-3-medium": "together-ai",
            "togetherai:deepcogito/cogito-v2-preview-llama-405B": "together-ai",
            "togetherai:deepcogito/cogito-v2-preview-llama-70B": "together-ai",
            "togetherai:minimax/video-01-director": "together-ai",
            "togetherai:togethercomputer/m2-bert-80M-32k-retrieval": "together-ai",
            "togetherai:deepseek-ai/DeepSeek-R1-0528-tput": "together-ai",
            "togetherai:google/flash-image-2.5": "together-ai",
            "togetherai:meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8": "together-ai",
            "togetherai:moonshotai/Kimi-K2-Thinking": "together-ai",
            "togetherai:Qwen/Qwen3-Next-80B-A3B-Instruct": "together-ai",
            "togetherai:ServiceNow-AI/Apriel-1.5-15b-Thinker": "together-ai",
            "togetherai:scb10x/scb10x-typhoon-2-1-gemma3-12b": "together-ai",
            "togetherai:meta-llama/Llama-Guard-4-12B": "together-ai",
            "togetherai:HiDream-ai/HiDream-I1-Fast": "together-ai",
            "togetherai:Wan-AI/Wan2.2-T2V-A14B": "together-ai",
            "togetherai:ByteDance/Seedance-1.0-pro": "together-ai",
            "togetherai:google/veo-3.0-fast-audio": "together-ai",
            "togetherai:vidu/vidu-q1": "together-ai",
            "togetherai:intfloat/multilingual-e5-large-instruct": "together-ai",
            "togetherai:meta-llama/Llama-4-Scout-17B-16E-Instruct": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": "together-ai",
            "togetherai:ByteDance-Seed/Seedream-3.0": "together-ai",
            "togetherai:ByteDance-Seed/Seedream-4.0": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3.1-405B-Instruct-Lite-Pro": "together-ai",
            "togetherai:meta-llama/Llama-3.2-3B-Instruct-Turbo": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-kontext-max": "together-ai",
            "togetherai:ideogram/ideogram-3.0": "together-ai",
            "togetherai:mixedbread-ai/Mxbai-Rerank-Large-V2": "together-ai",
            "togetherai:Salesforce/Llama-Rank-V1": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-schnell": "together-ai",
            "togetherai:deepseek-ai/DeepSeek-R1-Distill-Llama-70B": "together-ai",
            "togetherai:Qwen/Qwen2.5-VL-72B-Instruct": "together-ai",
            "togetherai:meta-llama/Llama-3-70b-chat-hf": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-kontext-dev": "together-ai",
            "togetherai:zai-org/GLM-4.6": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-pro": "together-ai",
            "togetherai:black-forest-labs/FLUX.1.1-pro": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3-70B-Instruct-Turbo": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-schnell-Free": "together-ai",
            "togetherai:Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8": "together-ai",
            "togetherai:black-forest-labs/FLUX.1-kontext-pro": "together-ai",
            "togetherai:mistralai/Mixtral-8x7B-Instruct-v0.1": "together-ai",
            "togetherai:nvidia/NVIDIA-Nemotron-Nano-9B-v2": "together-ai",
            "togetherai:openai/gpt-oss-120b": "together-ai",
            "togetherai:openai/sora-2": "together-ai",
            "togetherai:kwaivgI/kling-2.1-standard": "together-ai",
            "togetherai:google/imagen-4.0-fast": "together-ai",
            "togetherai:Qwen/Qwen2.5-7B-Instruct-Turbo": "together-ai",
            "togetherai:mistralai/Mistral-7B-Instruct-v0.3": "together-ai",
            "togetherai:google/gemma-3n-E4B-it": "together-ai",
            "togetherai:deepseek-ai/DeepSeek-V3": "together-ai",
            "togetherai:kwaivgI/kling-2.1-master": "together-ai",
            "togetherai:google/veo-3.0-audio": "together-ai",
            "togetherai:Rundiffusion/Juggernaut-Lightning-Flux": "together-ai",
            "togetherai:Wan-AI/Wan2.2-I2V-A14B": "together-ai",
            "togetherai:google/veo-2.0": "together-ai",
            "togetherai:google/veo-3.0-fast": "together-ai",
            "togetherai:kwaivgI/kling-1.6-pro": "together-ai",
            "togetherai:vidu/vidu-2.0": "together-ai",
            "togetherai:kwaivgI/kling-2.1-pro": "together-ai",
            "togetherai:Virtue-AI/VirtueGuard-Text-Lite": "together-ai",
            "togetherai:Qwen/Qwen3-235B-A22B-Instruct-2507-tput": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3-8B-Instruct-Lite": "together-ai",
            "togetherai:Qwen/Qwen3-235B-A22B-fp8-tput": "together-ai",
            "togetherai:togethercomputer/Refuel-Llm-V2-Small": "together-ai",
            "togetherai:arize-ai/qwen-2-1.5b-instruct": "together-ai",
            "togetherai:moonshotai/Kimi-K2-Instruct-0905": "together-ai",
            "togetherai:deepcogito/cogito-v2-preview-llama-109B-MoE": "together-ai",
            "togetherai:hexgrad/Kokoro-82M": "together-ai",
            "togetherai:google/gemini-3-pro-image": "together-ai",
            "togetherai:mercor/cwm": "together-ai",
            "togetherai:keith-aditya/kimi-k2-instruct": "together-ai",
            "togetherai:pangram/mistral-small-2501": "together-ai",
            "togetherai:black-forest-labs/FLUX.2-pro": "together-ai",
            "togetherai:black-forest-labs/FLUX.2-dev": "together-ai",
            "togetherai:zai-org/GLM-4.6": "together-ai",
            "togetherai:openai/whisper-large-v3": "together-ai",
            "togetherai:canopylabs/orpheus-3b-0.1-ft": "together-ai",
            "togetherai:meta-llama/Llama-3.1-405B-Instruct": "together-ai",
            "togetherai:meta-llama/Llama-3-70B-hf": "together-ai",
            "togetherai:Qwen/Qwen3-235B-A22B-Thinking-2507": "together-ai",
            "togetherai:Qwen/Qwen2.5-72B-Instruct": "together-ai",
            "togetherai:openai/gpt-oss-20b": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3.1-70B-Instruct-Reference": "together-ai",
            "togetherai:BAAI/bge-large-en-v1.5": "together-ai",
            "togetherai:meta-llama/Llama-3.2-1B-Instruct": "together-ai",
            "togetherai:Qwen/Qwen2.5-14B-Instruct": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3.1-8B-Instruct-Reference": "together-ai",
            "togetherai:meta-llama/Meta-Llama-3-8B-Instruct": "together-ai",
            "togetherai:BAAI/bge-base-en-v1.5": "together-ai",
            "togetherai:deepseek-ai/DeepSeek-V3.1": "together-ai",
            "togetherai:mistralai/Mistral-7B-Instruct-v0.2": "together-ai",
            # OpenRouter models
            "openrouter:anthropic/claude-opus-4.5": "openrouter",
            "openrouter:openrouter/bert-nebulon-alpha": "openrouter",
            "openrouter:allenai/olmo-3-32b-think": "openrouter",
            "openrouter:allenai/olmo-3-7b-instruct": "openrouter",
            "openrouter:allenai/olmo-3-7b-think": "openrouter",
            "openrouter:google/gemini-3-pro-image-preview": "openrouter",
            "openrouter:x-ai/grok-4.1-fast:free": "openrouter",
            "openrouter:google/gemini-3-pro-preview": "openrouter",
            "openrouter:deepcogito/cogito-v2.1-671b": "openrouter",
            "openrouter:openai/gpt-5.1": "openrouter",
            "openrouter:openai/gpt-5.1-chat": "openrouter",
            "openrouter:openai/gpt-5.1-codex": "openrouter",
            "openrouter:openai/gpt-5.1-codex-mini": "openrouter",
            "openrouter:kwaipilot/kat-coder-pro:free": "openrouter",
            "openrouter:moonshotai/kimi-linear-48b-a3b-instruct": "openrouter",
            "openrouter:moonshotai/kimi-k2-thinking": "openrouter",
            "openrouter:amazon/nova-premier-v1": "openrouter",
            "openrouter:perplexity/sonar-pro-search": "openrouter",
            "openrouter:mistralai/voxtral-small-24b-2507": "openrouter",
            "openrouter:openai/gpt-oss-safeguard-20b": "openrouter",
            "openrouter:nvidia/nemotron-nano-12b-v2-vl:free": "openrouter",
            "openrouter:nvidia/nemotron-nano-12b-v2-vl": "openrouter",
            "openrouter:minimax/minimax-m2": "openrouter",
            "openrouter:liquid/lfm2-8b-a1b": "openrouter",
            "openrouter:liquid/lfm-2.2-6b": "openrouter",
            "openrouter:ibm-granite/granite-4.0-h-micro": "openrouter",
            "openrouter:deepcogito/cogito-v2-preview-llama-405b": "openrouter",
            "openrouter:openai/gpt-5-image-mini": "openrouter",
            "openrouter:anthropic/claude-haiku-4.5": "openrouter",
            "openrouter:qwen/qwen3-vl-8b-thinking": "openrouter",
            "openrouter:qwen/qwen3-vl-8b-instruct": "openrouter",
            "openrouter:openai/gpt-5-image": "openrouter",
            "openrouter:openai/o3-deep-research": "openrouter",
            "openrouter:openai/o4-mini-deep-research": "openrouter",
            "openrouter:nvidia/llama-3.3-nemotron-super-49b-v1.5": "openrouter",
            "openrouter:baidu/ernie-4.5-21b-a3b-thinking": "openrouter",
            "openrouter:google/gemini-2.5-flash-image": "openrouter",
            "openrouter:qwen/qwen3-vl-30b-a3b-thinking": "openrouter",
            "openrouter:qwen/qwen3-vl-30b-a3b-instruct": "openrouter",
            "openrouter:qwen/qwen3-max": "openrouter",
            "openrouter:qwen/qwen3-coder-plus": "openrouter",
            "openrouter:openai/gpt-5-codex": "openrouter",
            "openrouter:deepseek/deepseek-v3.1-terminus:exacto": "openrouter",
            "openrouter:deepseek/deepseek-v3.1-terminus": "openrouter",
            "openrouter:x-ai/grok-4-fast": "openrouter",
            "openrouter:alibaba/tongyi-deepresearch-30b-a3b:free": "openrouter",
            "openrouter:alibaba/tongyi-deepresearch-30b-a3b": "openrouter",
            "openrouter:qwen/qwen3-coder-flash": "openrouter",
            "openrouter:opengvlab/internvl3-78b": "openrouter",
            "openrouter:qwen/qwen3-next-80b-a3b-thinking": "openrouter",
            "openrouter:qwen/qwen3-next-80b-a3b-instruct": "openrouter",
            "openrouter:meituan/longcat-flash-chat:free": "openrouter",
            "openrouter:meituan/longcat-flash-chat": "openrouter",
            "openrouter:qwen/qwen-plus-2025-07-28": "openrouter",
            "openrouter:qwen/qwen-plus-2025-07-28:thinking": "openrouter",
            "openrouter:nvidia/nemotron-nano-9b-v2:free": "openrouter",
            "openrouter:nvidia/nemotron-nano-9b-v2": "openrouter",
            "openrouter:moonshotai/kimi-k2-0905": "openrouter",
            "openrouter:moonshotai/kimi-k2-0905:exacto": "openrouter",
            "openrouter:deepcogito/cogito-v2-preview-llama-70b": "openrouter",
            "openrouter:deepcogito/cogito-v2-preview-llama-109b-moe": "openrouter",
            "openrouter:deepcogito/cogito-v2-preview-deepseek-671b": "openrouter",
            "openrouter:stepfun-ai/step3": "openrouter",
            "openrouter:qwen/qwen3-30b-a3b-thinking-2507": "openrouter",
            "openrouter:x-ai/grok-code-fast-1": "openrouter",
            "openrouter:nousresearch/hermes-4-70b": "openrouter",
            "openrouter:nousresearch/hermes-4-405b": "openrouter",
            "openrouter:google/gemini-2.5-flash-image-preview": "openrouter",
            "openrouter:deepseek/deepseek-chat-v3.1": "openrouter",
            "openrouter:openai/gpt-4o-audio-preview": "openrouter",
            "openrouter:mistralai/mistral-medium-3.1": "openrouter",
            "openrouter:baidu/ernie-4.5-21b-a3b": "openrouter",
            "openrouter:baidu/ernie-4.5-vl-28b-a3b": "openrouter",
            "openrouter:z-ai/glm-4.5": "openrouter",
            "openrouter:ai21/jamba-mini-1.7": "openrouter",
            "openrouter:ai21/jamba-large-1.7": "openrouter",
            "openrouter:openai/gpt-5-chat": "openrouter",
            "openrouter:openai/gpt-5": "openrouter",
            "openrouter:openai/gpt-5-mini": "openrouter",
            "openrouter:openai/gpt-5-nano": "openrouter",
            "openrouter:openai/gpt-oss-120b:exacto": "openrouter",
            "openrouter:openai/gpt-oss-120b": "openrouter",
            "openrouter:openai/gpt-oss-20b:free": "openrouter",
            "openrouter:openai/gpt-oss-20b": "openrouter",
            "openrouter:anthropic/claude-opus-4.1": "openrouter",
            "openrouter:anthropic/claude-sonnet-4": "openrouter",
            "openrouter:mistralai/codestral-2508": "openrouter",
            "openrouter:qwen/qwen3-coder-30b-a3b-instruct": "openrouter",
            "openrouter:qwen/qwen3-30b-a3b-instruct-2507": "openrouter",
            "openrouter:z-ai/glm-4.5": "openrouter",
            "openrouter:z-ai/glm-4.5-air:free": "openrouter",
            "openrouter:z-ai/glm-4.5-air": "openrouter",
            "openrouter:qwen/qwen3-235b-a22b-thinking-2507": "openrouter",
            "openrouter:z-ai/glm-4-32b": "openrouter",
            "openrouter:qwen/qwen3-coder:free": "openrouter",
            "openrouter:qwen/qwen3-coder": "openrouter",
            "openrouter:qwen/qwen3-coder:exacto": "openrouter",
            "openrouter:bytedance/ui-tars-1.5-7b": "openrouter",
            "openrouter:google/gemini-2.5-flash-lite": "openrouter",
            "openrouter:qwen/qwen3-235b-a22b-2507": "openrouter",
            "openrouter:switchpoint/router": "openrouter",
            "openrouter:moonshotai/kimi-k2:free": "openrouter",
            "openrouter:moonshotai/kimi-k2": "openrouter",
            "openrouter:thudm/glm-4.1v-9b-thinking": "openrouter",
            "openrouter:mistralai/devstral-medium": "openrouter",
            "openrouter:mistralai/devstral-small": "openrouter",
            "openrouter:cognitivecomputations/dolphin-mistral-24b-venice-edition:free": "openrouter",
            "openrouter:x-ai/grok-4": "openrouter",
            "openrouter:google/gemma-3n-e2b-it:free": "openrouter",
            "openrouter:tencent/hunyuan-a13b-instruct": "openrouter",
            "openrouter:tngtech/deepseek-r1t2-chimera:free": "openrouter",
            "openrouter:tngtech/deepseek-r1t2-chimera": "openrouter",
            "openrouter:morph/morph-v3-large": "openrouter",
            "openrouter:morph/morph-v3-fast": "openrouter",
            "openrouter:baidu/ernie-4.5-vl-424b-a47b": "openrouter",
            "openrouter:baidu/ernie-4.5-300b-a47b": "openrouter",
            "openrouter:thedrummer/anubis-70b-v1.1": "openrouter",
            "openrouter:inception/mercury": "openrouter",
            "openrouter:mistralai/mistral-small-3.2-24b-instruct:free": "openrouter",
            "openrouter:mistralai/mistral-small-3.2-24b-instruct": "openrouter",
            "openrouter:minimax/minimax-m1": "openrouter",
            "openrouter:google/gemini-2.5-flash": "openrouter",
            "openrouter:google/gemini-2.5-pro": "openrouter",
            "openrouter:moonshotai/kimi-dev-72b": "openrouter",
            "openrouter:openai/o3-pro": "openrouter",
            "openrouter:x-ai/grok-3-mini": "openrouter",
            "openrouter:x-ai/grok-3": "openrouter",
            "openrouter:mistralai/magistral-small-2506": "openrouter",
            "openrouter:mistralai/magistral-medium-2506:thinking": "openrouter",
            "openrouter:mistralai/magistral-medium-2506": "openrouter",
            "openrouter:google/gemini-2.5-pro-preview": "openrouter",
            "openrouter:deepseek/deepseek-r1-0528-qwen3-8b:free": "openrouter",
            "openrouter:deepseek/deepseek-r1-0528-qwen3-8b": "openrouter",
            "openrouter:deepseek/deepseek-r1-0528:free": "openrouter",
            "openrouter:deepseek/deepseek-r1-0528": "openrouter",
            "openrouter:minimax/minimax-01": "openrouter",
            "openrouter:mistralai/codestral-2501": "openrouter",
            "openrouter:microsoft/phi-4": "openrouter",
            "openrouter:sao10k/l3.1-70b-hanami-x1": "openrouter",
            "openrouter:deepseek/deepseek-chat": "openrouter",
            "openrouter:sao10k/l3.3-euryale-70b": "openrouter",
            "openrouter:openai/o1": "openrouter",
            "openrouter:cohere/command-a": "openrouter",
            "openrouter:google/gemini-2.0-flash-lite-001": "openrouter",
            "openrouter:anthropic/claude-3.7-sonnet:thinking": "openrouter",
            "openrouter:anthropic/claude-3.7-sonnet": "openrouter",
            "openrouter:mistralai/mistral-saba": "openrouter",
            "openrouter:meta-llama/llama-guard-4-12b": "openrouter",
            "openrouter:openai/o3-mini-high": "openrouter",
            "openrouter:google/gemini-2.0-flash-001": "openrouter",
            "openrouter:qwen/qwen-vl-plus": "openrouter",
            "openrouter:aion-labs/aion-1.0": "openrouter",
            "openrouter:aion-labs/aion-1.0-mini": "openrouter",
            "openrouter:aion-labs/aion-rp-llama-3.1-8b": "openrouter",
            "openrouter:qwen/qwen-vl-max": "openrouter",
            "openrouter:qwen/qwen-turbo": "openrouter",
            "openrouter:qwen/qwen2.5-vl-72b-instruct": "openrouter",
            "openrouter:qwen/qwen-plus": "openrouter",
            "openrouter:qwen/qwen-max": "openrouter",
            "openrouter:openai/o3-mini": "openrouter",
            "openrouter:mistralai/mistral-small-24b-instruct-2501:free": "openrouter",
            "openrouter:mistralai/mistral-small-24b-instruct-2501": "openrouter",
            "openrouter:deepseek/deepseek-r1-distill-qwen-32b": "openrouter",
            "openrouter:deepseek/deepseek-r1-distill-qwen-14b": "openrouter",
            "openrouter:perplexity/sonar-reasoning": "openrouter",
            "openrouter:perplexity/sonar": "openrouter",
            "openrouter:deepseek/deepseek-r1-distill-llama-70b:free": "openrouter",
            "openrouter:deepseek/deepseek-r1-distill-llama-70b": "openrouter",
            "openrouter:deepseek/deepseek-r1:free": "openrouter",
            "openrouter:deepseek/deepseek-r1": "openrouter",
            "openrouter:cohere/command-r7b-12-2024": "openrouter",
            "openrouter:cohere/command-r-plus-08-2024": "openrouter",
            "openrouter:sao10k/l3.1-euryale-70b": "openrouter",
            "openrouter:qwen/qwen2.5-vl-7b-instruct": "openrouter",
            "openrouter:microsoft/phi-3.5-mini-128k-instruct": "openrouter",
            "openrouter:nousresearch/hermes-3-llama-3.1-70b": "openrouter",
            "openrouter:nousresearch/hermes-3-llama-3.1-405b:free": "openrouter",
            "openrouter:nousresearch/hermes-3-llama-3.1-405b": "openrouter",
            "openrouter:openai/chatgpt-4o-latest": "openrouter",
            "openrouter:sao10k/l3-lunaris-8b": "openrouter",
            "openrouter:openai/gpt-4o-2024-11-20": "openrouter",
            "openrouter:meta-llama/llama-3.1-405b": "openrouter",
            "openrouter:meta-llama/llama-3.1-8b-instruct": "openrouter",
            "openrouter:meta-llama/llama-3.1-405b-instruct": "openrouter",
            "openrouter:meta-llama/llama-3.1-70b-instruct": "openrouter",
            "openrouter:mistralai/mistral-nemo:free": "openrouter",
            "openrouter:mistralai/mistral-nemo": "openrouter",
            "openrouter:openai/gpt-4o-mini-2024-07-18": "openrouter",
            "openrouter:openai/gpt-4o-mini": "openrouter",
            "openrouter:google/gemma-2-27b-it": "openrouter",
            "openrouter:google/gemma-2-9b-it": "openrouter",
            "openrouter:sao10k/l3-euryale-70b": "openrouter",
            "openrouter:nousresearch/hermes-2-pro-llama-3-8b": "openrouter",
            "openrouter:mistralai/mistral-7b-instruct:free": "openrouter",
            "openrouter:mistralai/mistral-7b-instruct": "openrouter",
            "openrouter:mistralai/mistral-7b-instruct-v0.3": "openrouter",
            "openrouter:microsoft/phi-3-mini-128k-instruct": "openrouter",
            "openrouter:microsoft/phi-3-medium-128k-instruct": "openrouter",
            "openrouter:meta-llama/llama-guard-2-8b": "openrouter",
            "openrouter:openai/gpt-4o-2024-05-13": "openrouter",
            "openrouter:openai/gpt-4o": "openrouter",
            "openrouter:openai/gpt-4o:extended": "openrouter",
            "openrouter:meta-llama/llama-3-70b-instruct": "openrouter",
            "openrouter:meta-llama/llama-3-8b-instruct": "openrouter",
            "openrouter:mistralai/mixtral-8x22b-instruct": "openrouter",
            "openrouter:microsoft/wizardlm-2-8x22b": "openrouter",
            "openrouter:openai/gpt-4-turbo": "openrouter",
            "openrouter:anthropic/claude-3-haiku": "openrouter",
            "openrouter:anthropic/claude-3-opus": "openrouter",
            "openrouter:mistralai/mistral-large": "openrouter",
            "openrouter:openai/gpt-3.5-turbo-0613": "openrouter",
            "openrouter:openai/gpt-4-turbo-preview": "openrouter",
            "openrouter:mistralai/mistral-small": "openrouter",
            "openrouter:mistralai/mistral-tiny": "openrouter",
            "openrouter:mistralai/mistral-7b-instruct-v0.2": "openrouter",
            "openrouter:mistralai/mixtral-8x7b-instruct": "openrouter",
            "openrouter:neversleep/noromaid-20b": "openrouter",
            "openrouter:alpindale/goliath-120b": "openrouter",
            "openrouter:openrouter/auto": "openrouter",
            "openrouter:openai/gpt-4-1106-preview": "openrouter",
            "openrouter:openai/gpt-3.5-turbo-instruct": "openrouter",
            "openrouter:openai/gpt-3.5-turbo-16k": "openrouter",
            "openrouter:mancer/weaver": "openrouter",
            "openrouter:undi95/remm-slerp-l2-13b": "openrouter",
            "openrouter:gryphe/mythomax-l2-13b": "openrouter",
            "openrouter:openai/gpt-4-0314": "openrouter",
            "openrouter:openai/gpt-4": "openrouter",
            "openrouter:openai/gpt-3.5-turbo": "openrouter",
            # Special/test models
            "model-fallback-test-1": "openai-completion",
            "costly": "openai-completion",
            "abuse": "openai-completion",
            "fake": "openai-completion",
            # Additional OpenRouter models
            "openrouter:alfredpros/codellama-7b-instruct-solidity": "openrouter",
            "openrouter:allenai/olmo-2-0325-32b-instruct": "openrouter",
            "openrouter:amazon/nova-lite-v1": "openrouter",
            "openrouter:amazon/nova-micro-v1": "openrouter",
            "openrouter:amazon/nova-pro-v1": "openrouter",
            "openrouter:anthracite-org/magnum-v4-72b": "openrouter",
            "openrouter:anthropic/claude-3.5-haiku": "openrouter",
            "openrouter:anthropic/claude-3.5-haiku-20241022": "openrouter",
            "openrouter:anthropic/claude-3.5-sonnet": "openrouter",
            "openrouter:anthropic/claude-opus-4": "openrouter",
            "openrouter:arcee-ai/coder-large": "openrouter",
            "openrouter:arcee-ai/maestro-reasoning": "openrouter",
            "openrouter:arcee-ai/spotlight": "openrouter",
            "openrouter:arcee-ai/virtuoso-large": "openrouter",
            "openrouter:arliai/qwq-32b-arliai-rpr-v1": "openrouter",
            "openrouter:arliai/qwq-32b-arliai-rpr-v1:free": "openrouter",
            "openrouter:cohere/command-r-08-2024": "openrouter",
            "openrouter:deepseek/deepseek-chat-v3-0324": "openrouter",
            "openrouter:deepseek/deepseek-chat-v3-0324:free": "openrouter",
            "openrouter:deepseek/deepseek-prover-v2": "openrouter",
            "openrouter:eleutherai/llemma_7b": "openrouter",
            "openrouter:google/gemini-2.0-flash-exp:free": "openrouter",
            "openrouter:google/gemini-2.5-pro-preview-05-06": "openrouter",
            "openrouter:google/gemma-3-12b-it": "openrouter",
            "openrouter:google/gemma-3-12b-it:free": "openrouter",
            "openrouter:google/gemma-3-27b-it": "openrouter",
            "openrouter:google/gemma-3-27b-it:free": "openrouter",
            "openrouter:google/gemma-3-4b-it": "openrouter",
            "openrouter:google/gemma-3-4b-it:free": "openrouter",
            "openrouter:google/gemma-3n-e4b-it": "openrouter",
            "openrouter:google/gemma-3n-e4b-it:free": "openrouter",
            "openrouter:inception/mercury-coder": "openrouter",
            "openrouter:inflection/inflection-3-pi": "openrouter",
            "openrouter:inflection/inflection-3-productivity": "openrouter",
            "openrouter:meta-llama/llama-3.2-11b-vision-instruct": "openrouter",
            "openrouter:meta-llama/llama-3.2-1b-instruct": "openrouter",
            "openrouter:meta-llama/llama-3.2-3b-instruct": "openrouter",
            "openrouter:meta-llama/llama-3.2-3b-instruct:free": "openrouter",
            "openrouter:meta-llama/llama-3.2-90b-vision-instruct": "openrouter",
            "openrouter:meta-llama/llama-3.3-70b-instruct": "openrouter",
            "openrouter:meta-llama/llama-3.3-70b-instruct:free": "openrouter",
            "openrouter:meta-llama/llama-4-maverick": "openrouter",
            "openrouter:meta-llama/llama-4-scout": "openrouter",
            "openrouter:meta-llama/llama-guard-3-8b": "openrouter",
            "openrouter:microsoft/mai-ds-r1": "openrouter",
            "openrouter:microsoft/mai-ds-r1:free": "openrouter",
            "openrouter:microsoft/phi-4-multimodal-instruct": "openrouter",
            "openrouter:microsoft/phi-4-reasoning-plus": "openrouter",
            "openrouter:mistralai/devstral-small-2505": "openrouter",
            "openrouter:mistralai/ministral-3b": "openrouter",
            "openrouter:mistralai/ministral-8b": "openrouter",
            "openrouter:mistralai/mistral-7b-instruct-v0.1": "openrouter",
            "openrouter:mistralai/mistral-large-2407": "openrouter",
            "openrouter:mistralai/mistral-large-2411": "openrouter",
            "openrouter:mistralai/mistral-medium-3": "openrouter",
            "openrouter:mistralai/mistral-small-3.1-24b-instruct": "openrouter",
            "openrouter:mistralai/mistral-small-3.1-24b-instruct:free": "openrouter",
            "openrouter:mistralai/pixtral-12b": "openrouter",
            "openrouter:mistralai/pixtral-large-2411": "openrouter",
            "openrouter:neversleep/llama-3.1-lumimaid-8b": "openrouter",
            "openrouter:nousresearch/deephermes-3-mistral-24b-preview": "openrouter",
            "openrouter:nvidia/llama-3.1-nemotron-70b-instruct": "openrouter",
            "openrouter:nvidia/llama-3.1-nemotron-ultra-253b-v1": "openrouter",
            "openrouter:openai/codex-mini": "openrouter",
            "openrouter:openai/gpt-4.1": "openrouter",
            "openrouter:openai/gpt-4.1-mini": "openrouter",
            "openrouter:openai/gpt-4.1-nano": "openrouter",
            "openrouter:openai/gpt-4o-2024-08-06": "openrouter",
            "openrouter:openai/gpt-4o-mini-search-preview": "openrouter",
            "openrouter:openai/gpt-4o-search-preview": "openrouter",
            "openrouter:openai/o1-pro": "openrouter",
            "openrouter:openai/o3": "openrouter",
            "openrouter:openai/o4-mini": "openrouter",
            "openrouter:openai/o4-mini-high": "openrouter",
            "openrouter:perplexity/sonar-deep-research": "openrouter",
            "openrouter:perplexity/sonar-pro": "openrouter",
            "openrouter:perplexity/sonar-reasoning-pro": "openrouter",
            "openrouter:qwen/qwen-2.5-72b-instruct": "openrouter",
            "openrouter:qwen/qwen-2.5-72b-instruct:free": "openrouter",
            "openrouter:qwen/qwen-2.5-7b-instruct": "openrouter",
            "openrouter:qwen/qwen-2.5-coder-32b-instruct": "openrouter",
            "openrouter:qwen/qwen-2.5-coder-32b-instruct:free": "openrouter",
            "openrouter:qwen/qwen-2.5-vl-7b-instruct": "openrouter",
            "openrouter:qwen/qwen2.5-coder-7b-instruct": "openrouter",
            "openrouter:qwen/qwen2.5-vl-32b-instruct": "openrouter",
            "openrouter:qwen/qwen2.5-vl-32b-instruct:free": "openrouter",
            "openrouter:qwen/qwen3-14b": "openrouter",
            "openrouter:qwen/qwen3-14b:free": "openrouter",
            "openrouter:qwen/qwen3-235b-a22b": "openrouter",
            "openrouter:qwen/qwen3-235b-a22b:free": "openrouter",
            "openrouter:qwen/qwen3-30b-a3b": "openrouter",
            "openrouter:qwen/qwen3-30b-a3b:free": "openrouter",
            "openrouter:qwen/qwen3-32b": "openrouter",
            "openrouter:qwen/qwen3-4b:free": "openrouter",
            "openrouter:qwen/qwen3-8b": "openrouter",
            "openrouter:qwen/qwq-32b": "openrouter",
            "openrouter:raifle/sorcererlm-8x22b": "openrouter",
            "openrouter:thedrummer/rocinante-12b": "openrouter",
            "openrouter:thedrummer/skyfall-36b-v2": "openrouter",
            "openrouter:thedrummer/unslopnemo-12b": "openrouter",
            "openrouter:tngtech/deepseek-r1t-chimera": "openrouter",
            "openrouter:tngtech/deepseek-r1t-chimera:free": "openrouter",
            "openrouter:x-ai/grok-3-beta": "openrouter",
            "openrouter:x-ai/grok-3-mini-beta": "openrouter",
            "openrouter:z-ai/glm-4.5v": "openrouter",
            # Additional TogetherAI models
            "togetherai:ByteDance/Seedance-1.0-lite": "together-ai",
            "togetherai:Meta-Llama/Llama-Guard-7b": "together-ai",
            "togetherai:kwaivgI/kling-2.0-master": "together-ai",
            "togetherai:meta-llama/Llama-Guard-3-11B-Vision-Turbo": "together-ai",
            "togetherai:openai/sora-2-pro": "together-ai",
            "togetherai:pixverse/pixverse-v5": "together-ai",
            "togetherai:stabilityai/stable-diffusion-xl-base-1.0": "together-ai",
        }
        # For these models, per puter.js docs, temperature must be 1 by default
        self.force_temperature_1_models = {
            "gpt-5-2025-08-07",
            "gpt-5-mini-2025-08-07",
            "gpt-5-nano-2025-08-07",
            "gpt-5.1",
            "gpt-5.1-codex",
            "gpt-5.1-codex-mini",
            "gpt-5.1-chat-latest",
            "o1",
            "o1-mini",
            "o1-pro",
            "o3",
            "o3-mini",
            "o4-mini",
        }
        self.fallback_models = [
            "gpt-5-nano",
            "gpt-4.1-nano",
            "gpt-4o-mini",
            "claude-3-5-sonnet-latest",
            "deepseek-chat",
        ]
        self.max_retries = 3
        self._models_cache = None
        self._cache_timestamp = None
        self._cache_ttl = timedelta(hours=1)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp ClientSession with proper SSL and timeout settings."""
        if self._session is None or self._session.closed:
            # Configure SSL context with certifi
            if self.ignore_ssl:
                ssl_context = False
            else:
                ssl_context = ssl.create_default_context(cafile=certifi.where())

            # Force IPv4 to avoid Windows semaphore timeout issues with IPv6
            connector = aiohttp.TCPConnector(ssl=ssl_context, family=socket.AF_INET, limit=100)

            # Explicit timeout
            timeout = aiohttp.ClientTimeout(total=60)

            self._session = aiohttp.ClientSession(
                headers=self.headers,
                connector=connector,
                timeout=timeout,
                trust_env=True,  # Respect system proxies
            )
        return self._session

    async def __aenter__(self):
        await self._get_session()
        if self.auto_update_models and self.token:
            await self.update_model_mappings()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def close(self):
        """Manually close the session."""
        if self._session:
            await self._session.close()

    async def get_available_models(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch the list of available AI models from the Puter.com API.

        Uses caching with a 1-hour TTL. The API returns a list of models,
        where each entry can be a string or an object with model details.

        Args:
            force_refresh: Force cache refresh.

        Returns:
            Dict with key 'models' - a list of models (strings or objects).
            If a model is an object, it may include: id, name, provider, driver, aliases, etc.

        Raises:
            aiohttp.ClientError: On request error when no cache is available.
            ValueError: On invalid API response format.
        """
        session = await self._get_session()

        # Cache check
        if (
            not force_refresh
            and self._models_cache is not None
            and self._cache_timestamp is not None
            and datetime.now() - self._cache_timestamp < self._cache_ttl
        ):
            models_count = len(self._models_cache.get("models", []))
            logger.info(f"Returning {models_count} models from cache")
            return self._models_cache

        url = "https://puter.com/puterai/chat/models"
        try:
            async with session.get(url, headers=self._get_auth_headers()) as response:
                response.raise_for_status()
                data: Dict[str, Any] = await response.json()

                # Normalize response shape
                if isinstance(data, list):
                    # Response is just a list of models
                    data = {"models": data}
                elif not isinstance(data, dict):
                    raise ValueError(
                        f"Unexpected API response format: expected dict or list, got {type(data)}"
                    )

                # Ensure the 'models' key exists
                if "models" not in data:
                    raise ValueError("API response is missing the 'models' key")

                models = data["models"]
                if not isinstance(models, list):
                    raise ValueError(f"The 'models' field must be a list, got {type(models)}")

                # Normalize models: keep strings as-is, preserve objects
                normalized_models = []
                for model in models:
                    if isinstance(model, str):
                        normalized_models.append(model)
                    elif isinstance(model, dict):
                        # Preserve model object as-is
                        normalized_models.append(model)
                    else:
                        logger.warning(f"Unexpected model type: {type(model)}, value: {model}")
                        # Try to coerce to string
                        normalized_models.append(str(model))

                result = {"models": normalized_models}
                self._models_cache = result
                self._cache_timestamp = datetime.now()
                logger.info(f"Fetched {len(normalized_models)} models from API")
                return result

        except aiohttp.ClientError as e:
            logger.error(f"Error fetching models: {e}")
            if self._models_cache is not None:
                logger.warning("Using cached models")
                return self._models_cache
            else:
                raise
        except (ValueError, KeyError) as e:
            logger.error(f"Error parsing API response: {e}")
            if self._models_cache is not None:
                logger.warning("Using cached models")
                return self._models_cache
            else:
                raise

    async def update_model_mappings(self) -> None:
        """Automatically refresh self.model_to_driver using available models.

        Uses driver info from the API when present; otherwise applies heuristics
        based on the model name.
        """
        models_data = await self.get_available_models()
        new_mappings: Dict[str, str] = {}

        for model_item in models_data["models"]:
            model_id: str = ""
            driver: Optional[str] = None
            provider: Optional[str] = None

            # Handle model object
            if isinstance(model_item, dict):
                # Extract model ID with safe conversion to string
                id_val = model_item.get("id")
                if id_val is not None:
                    model_id = str(id_val)
                else:
                    name_val = model_item.get("name")
                    if name_val is not None:
                        model_id = str(name_val)
                    else:
                        model_val = model_item.get("model")
                        if model_val is not None:
                            model_id = str(model_val)
                        else:
                            logger.warning(f"Model object without ID: {model_item}")
                            continue

                # Attempt to get driver and provider from the object
                driver = model_item.get("driver")
                provider = model_item.get("provider")

                # If driver is missing but provider is present, derive from provider
                if driver is None and provider is not None and isinstance(provider, str):
                    provider_lower = provider.lower()
                    if provider_lower in ("openai", "openai-completion"):
                        driver = "openai-completion"
                    elif provider_lower == "anthropic":
                        driver = "claude"
                    elif provider_lower == "mistral":
                        driver = "mistral"
                    elif provider_lower in ("xai", "x-ai"):
                        driver = "xai"
                    elif provider_lower == "deepseek":
                        driver = "deepseek"
                    elif provider_lower == "google":
                        driver = "google"
                    elif provider_lower in ("together-ai", "togetherai"):
                        driver = "together-ai"
                    elif provider_lower == "openrouter":
                        driver = "openrouter"

            # Handle model string
            elif isinstance(model_item, str):
                model_id = model_item
            else:
                logger.warning(f"Unexpected model item type: {type(model_item)}")
                continue

            # If driver is still unknown, apply heuristic
            if not driver:
                model_lower = model_id.lower()

                # Detect driver by prefix or content
                if model_id.startswith("openrouter:"):
                    driver = "openrouter"
                elif model_id.startswith("togetherai:"):
                    driver = "together-ai"
                elif "claude" in model_lower:
                    driver = "claude"
                elif (
                    "mistral" in model_lower
                    or "ministral" in model_lower
                    or "pixtral" in model_lower
                ):
                    driver = "mistral"
                elif "grok" in model_lower:
                    driver = "xai"
                elif "deepseek" in model_lower:
                    driver = "deepseek"
                elif "gemini" in model_lower:
                    driver = "google"
                elif model_id.startswith("gpt-") or model_id.startswith(("o1", "o3", "o4")):
                    driver = "openai-completion"
                elif "/" in model_id and not model_id.startswith(("openrouter:", "togetherai:")):
                    # Models containing "/" are usually TogetherAI
                    driver = "together-ai"
                else:
                    # Default to openai-completion
                    driver = "openai-completion"

            new_mappings[model_id] = driver

        # Update mapping
        updated_count = 0
        for model_id, driver in new_mappings.items():
            if model_id not in self.model_to_driver or self.model_to_driver[model_id] != driver:
                self.model_to_driver[model_id] = driver
                updated_count += 1

        logger.info(f"Mappings updated: {updated_count} new/changed of {len(new_mappings)} models")

    def _extract_model_id(self, model_item: Union[str, Dict[str, Any]]) -> str:
        """Extract a model ID from a string or object.

        Args:
            model_item: Model as a string or object.

        Returns:
            Model ID as string. For dict objects, checks fields 'id', 'name', 'model'
            in priority order. For other types, returns the string representation.
        """
        if isinstance(model_item, str):
            return model_item
        elif isinstance(model_item, dict):
            # Check for None explicitly to distinguish empty strings from missing fields
            id_val = model_item.get("id")
            if id_val is not None:
                return str(id_val)
            name_val = model_item.get("name")
            if name_val is not None:
                return str(name_val)
            model_val = model_item.get("model")
            if model_val is not None:
                return str(model_val)
            # Fall back to string representation to ensure no models are skipped
            return str(model_item)
        else:
            # For any other type, convert to string
            return str(model_item)

    def get_model_list(self, models_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get list of model IDs (strings) from models data.

        Args:
            models_data: Model data. If None, cache is used.

        Returns:
            List of model IDs as strings.
        """
        if models_data is None:
            models_data = self._models_cache or {"models": []}

        models = models_data.get("models", [])
        model_ids = []

        for model_item in models:
            model_id = self._extract_model_id(model_item)
            model_ids.append(model_id)

        return model_ids

    async def is_model_available(self, model_name: str) -> bool:
        """Check whether a model is available in the latest list.

        Args:
            model_name: Model name.

        Returns:
            bool: Whether the model is available.
        """
        models_data = await self.get_available_models()
        models = models_data.get("models", [])

        # Check presence in list
        for model_item in models:
            if isinstance(model_item, str):
                if model_item == model_name:
                    return True
            elif isinstance(model_item, dict):
                # Check various fields that may contain the model ID
                model_id = self._extract_model_id(model_item)
                if model_id == model_name:
                    return True
                # Also check aliases if present
                aliases = model_item.get("aliases", [])
                if isinstance(aliases, list) and model_name in aliases:
                    return True

        return False

    async def login(self, username: str, password: str) -> str:
        """
        Asynchronously login to Puter.
        """
        username = validate_string(username)
        password = validate_string(password)
        payload = {"username": username, "password": password}
        session = await self._get_session()

        try:
            async with session.post(self.login_url, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("proceed"):
                    self.token = data["token"]
                    logger.info("Login successful, token acquired")
                    return self.token
                else:
                    logger.warning("Login failed: Invalid credentials")
                    raise ValueError("Login failed. Please check your credentials.")
        except aiohttp.ClientError as e:
            logger.warning(f"Login error: {e}")
            raise ValueError(f"Login error: {e}")

    async def auth_is_signed_in(self) -> bool:
        headers = self._get_auth_headers()
        data = await self._request_json(
            "GET",
            f"{self.api_base}/auth/isSignedIn",
            headers=headers,
        )
        signed_in = data.get("signedIn") if isinstance(data, dict) else None
        return bool(signed_in)

    async def auth_get_user(self) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/auth/getUser",
            headers=headers,
        )

    async def auth_sign_out(self) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/auth/signOut",
            headers=headers,
            json_body={},
        )

    async def auth_get_monthly_usage(self) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/auth/getMonthlyUsage",
            headers=headers,
        )

    async def auth_get_detailed_app_usage(self) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/auth/getDetailedAppUsage",
            headers=headers,
        )

    async def apps_create(self, options: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/apps/create",
            headers=headers,
            json_body=options,
        )

    async def apps_get(self, app_id: str) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/apps/get",
            headers=headers,
            params={"app_id": validate_string(app_id)},
        )

    async def apps_list(self) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/apps/list",
            headers=headers,
        )

    async def apps_update(self, app_id: str, options: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        payload = dict(options)
        payload["app_id"] = validate_string(app_id)
        return await self._request_json(
            "POST",
            f"{self.api_base}/apps/update",
            headers=headers,
            json_body=payload,
        )

    async def apps_delete(self, app_id: str) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/apps/delete",
            headers=headers,
            json_body={"app_id": validate_string(app_id)},
        )

    async def hosting_create(self, options: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/hosting/create",
            headers=headers,
            json_body=options,
        )

    async def hosting_get(self, subdomain: str) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/hosting/get",
            headers=headers,
            params={"subdomain": validate_string(subdomain)},
        )

    async def hosting_list(self) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/hosting/list",
            headers=headers,
        )

    async def hosting_update(self, subdomain: str, options: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        payload = dict(options)
        payload["subdomain"] = validate_string(subdomain)
        return await self._request_json(
            "POST",
            f"{self.api_base}/hosting/update",
            headers=headers,
            json_body=payload,
        )

    async def hosting_delete(self, subdomain: str) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/hosting/delete",
            headers=headers,
            json_body={"subdomain": validate_string(subdomain)},
        )

    async def workers_create(self, options: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/workers/create",
            headers=headers,
            json_body=options,
        )

    async def workers_get(self, worker_name: str) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/workers/get",
            headers=headers,
            params={"workerName": validate_string(worker_name)},
        )

    async def workers_list(self) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/workers/list",
            headers=headers,
        )

    async def workers_delete(self, worker_name: str) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/workers/delete",
            headers=headers,
            json_body={"workerName": validate_string(worker_name)},
        )

    async def workers_exec(
        self,
        worker_url: str,
        *,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        data: Any = None,
        return_json: bool = False,
    ) -> Union[bytes, Dict[str, Any]]:
        url = validate_string(worker_url)
        hdrs = dict(headers or {})
        hdrs.update(self._get_auth_headers())
        if return_json:
            return await self._request_json(method, url, headers=hdrs, params=params, json_body=json_body, data=data)
        return await self._request_bytes(method, url, headers=hdrs, params=params, json_body=json_body, data=data)

    async def net_fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        data: Any = None,
        return_json: bool = False,
        include_auth: bool = False,
    ) -> Union[bytes, Dict[str, Any]]:
        target = validate_string(url)
        hdrs = dict(headers or {})
        if include_auth:
            hdrs.update(self._get_auth_headers())
        if return_json:
            return await self._request_json(method, target, headers=hdrs, params=params, json_body=json_body, data=data)
        return await self._request_bytes(method, target, headers=hdrs, params=params, json_body=json_body, data=data)

    def _get_auth_headers(self) -> Dict[str, str]:
        if not self.token:
            logger.error("Authentication error: No token available")
            raise ValueError("Not authenticated. Please login first.")
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        data: Any = None,
        raise_on_api_error: bool = True,
    ) -> Dict[str, Any]:
        session = await self._get_session()
        request_headers = headers or {}
        try:
            async with session.request(
                method,
                url,
                headers=request_headers,
                params=params,
                json=json_body,
                data=data,
            ) as response:
                response.raise_for_status()
                parsed: Any = await response.json()
                if raise_on_api_error and isinstance(parsed, dict) and parsed.get("success") is False:
                    error_data = parsed.get("error", {}) if isinstance(parsed.get("error"), dict) else {}
                    msg = error_data.get("message") or parsed.get("message") or "Unknown API error"
                    code = error_data.get("code")
                    raise ValueError(f"{msg}" + (f" (code: {code})" if code else ""))
                if not isinstance(parsed, dict):
                    raise ValueError(f"Unexpected JSON response type: {type(parsed)}")
                return parsed
        except aiohttp.ClientError as e:
            logger.warning(f"HTTP request failed: {method} {url}: {e}")
            raise

    async def _request_bytes(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        data: Any = None,
    ) -> bytes:
        session = await self._get_session()
        request_headers = headers or {}
        try:
            async with session.request(
                method,
                url,
                headers=request_headers,
                params=params,
                json=json_body,
                data=data,
            ) as response:
                response.raise_for_status()
                return await response.read()
        except aiohttp.ClientError as e:
            logger.warning(f"HTTP request failed: {method} {url}: {e}")
            raise

    async def drivers_call(
        self,
        interface: str,
        driver: str,
        method: str,
        args: Optional[Dict[str, Any]] = None,
        *,
        stream: bool = False,
        test_mode: bool = False,
    ) -> Union[Dict[str, Any], AsyncGenerator[bytes, None]]:
        interface = validate_string(interface)
        driver = validate_string(driver)
        method = validate_string(method)
        payload = {
            "interface": interface,
            "driver": driver,
            "method": method,
            "args": args or {},
            "stream": stream,
            "test_mode": test_mode,
        }
        headers = self._get_auth_headers()
        session = await self._get_session()

        if not stream:
            return await self._request_json(
                "POST",
                f"{self.api_base}/drivers/call",
                headers=headers,
                json_body=payload,
                raise_on_api_error=False,
            )

        async def stream_generator() -> AsyncGenerator[bytes, None]:
            async with session.post(
                f"{self.api_base}/drivers/call",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for chunk in response.content:
                    if chunk:
                        yield chunk

        return stream_generator()

    async def fs_write(
        self,
        path: str,
        content: Union[str, bytes, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Write content to a file in Puter FS asynchronously.
        """
        path = validate_path(path)
        headers = self._get_auth_headers()
        headers.pop("Content-Type")

        if isinstance(content, str):
            content = content.encode("utf-8")

        if not isinstance(content, bytes) and not hasattr(content, "read"):
            logger.warning("Invalid content type for fs_write")
            raise ValueError("Content must be str, bytes, or file-like object.")
        params: Dict[str, Any] = {"path": path}
        if options:
            for k in ("overwrite", "dedupeName", "createMissingParents"):
                if k in options:
                    params[k] = options[k]

        data = await self._request_json(
            "POST",
            f"{self.api_base}/write",
            headers=headers,
            params=params,
            data=content,
        )
        logger.info(f"File written successfully at {path}")
        return data

    async def fs_read(self, path: str) -> bytes:
        """
        Read file content from Puter FS asynchronously.
        """
        path = validate_path(path)
        headers = self._get_auth_headers()
        content = await self._request_bytes(
            "GET",
            f"{self.api_base}/read",
            headers=headers,
            params={"path": path},
        )
        logger.info(f"File read successfully from {path}")
        return content

    async def fs_delete(self, path: str) -> None:
        """
        Delete a file or directory in Puter FS asynchronously.
        """
        path = validate_path(path)
        headers = self._get_auth_headers()
        await self._request_json(
            "POST",
            f"{self.api_base}/delete",
            headers=headers,
            params={"path": path},
            json_body={},
        )
        logger.info(f"File deleted successfully at {path}")

    async def fs_mkdir(self, path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        path = validate_path(path)
        headers = self._get_auth_headers()
        payload = {"path": path}
        if options:
            payload.update(options)
        return await self._request_json(
            "POST",
            f"{self.api_base}/mkdir",
            headers=headers,
            json_body=payload,
        )

    async def fs_readdir(self, path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        path = validate_path(path)
        headers = self._get_auth_headers()
        payload = {"path": path}
        if options:
            payload.update(options)
        return await self._request_json(
            "POST",
            f"{self.api_base}/readdir",
            headers=headers,
            json_body=payload,
        )

    async def fs_rename(
        self, source: str, destination: str, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        source = validate_path(source)
        destination = validate_path(destination)
        headers = self._get_auth_headers()
        payload = {"source": source, "destination": destination}
        if options:
            payload.update(options)
        return await self._request_json(
            "POST",
            f"{self.api_base}/rename",
            headers=headers,
            json_body=payload,
        )

    async def fs_copy(
        self, source: str, destination: str, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        source = validate_path(source)
        destination = validate_path(destination)
        headers = self._get_auth_headers()
        payload = {"source": source, "destination": destination}
        if options:
            payload.update(options)
        return await self._request_json(
            "POST",
            f"{self.api_base}/copy",
            headers=headers,
            json_body=payload,
        )

    async def fs_move(
        self, source: str, destination: str, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        source = validate_path(source)
        destination = validate_path(destination)
        headers = self._get_auth_headers()
        payload = {"source": source, "destination": destination}
        if options:
            payload.update(options)
        return await self._request_json(
            "POST",
            f"{self.api_base}/move",
            headers=headers,
            json_body=payload,
        )

    async def fs_stat(self, path: str) -> Dict[str, Any]:
        path = validate_path(path)
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/stat",
            headers=headers,
            params={"path": path},
        )

    async def fs_space(self) -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "GET",
            f"{self.api_base}/space",
            headers=headers,
        )

    async def fs_get_read_url(self, path: str, options: Optional[Dict[str, Any]] = None) -> str:
        path = validate_path(path)
        headers = self._get_auth_headers()
        params: Dict[str, Any] = {"path": path}
        if options:
            params.update(options)
        data = await self._request_json(
            "GET",
            f"{self.api_base}/getReadURL",
            headers=headers,
            params=params,
        )
        url = data.get("url") or data.get("read_url") or data.get("readURL")
        if not isinstance(url, str) or not url:
            raise ValueError(f"Unexpected response format: {data}")
        return url

    async def fs_upload(
        self,
        files: Union[Any, List[Any]],
        destination: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(files, list):
            files = [files]
        form = aiohttp.FormData()
        for idx, f in enumerate(files):
            form.add_field(f"file{idx}", f)
        if destination is not None:
            form.add_field("destination", validate_path(destination))
        if options:
            for k, v in options.items():
                form.add_field(k, str(v).lower() if isinstance(v, bool) else str(v))
        headers = self._get_auth_headers()
        headers.pop("Content-Type", None)
        return await self._request_json(
            "POST",
            f"{self.api_base}/upload",
            headers=headers,
            data=form,
        )

    async def kv_set(self, key: str, value: Any) -> Any:
        """
        Set a value in the Key-Value store.
        """
        key = validate_string(key)
        payload = {"key": key, "value": value}
        headers = self._get_auth_headers()
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/set",
            headers=headers,
            json_body=payload,
        )
        logger.info(f"KV set successful for key: {key}")
        return data

    async def kv_get(self, key: str) -> Any:
        """
        Get a value from the Key-Value store.
        """
        key = validate_string(key)
        payload = {"key": key}
        headers = self._get_auth_headers()
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/get",
            headers=headers,
            json_body=payload,
            raise_on_api_error=False,
        )
        if data.get("success", True) is False:
            return None
        return data.get("value")

    async def kv_delete(self, key: str) -> bool:
        """
        Delete a value from the Key-Value store.
        """
        key = validate_string(key)
        payload = {"key": key}
        headers = self._get_auth_headers()
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/delete",
            headers=headers,
            json_body=payload,
        )
        return data.get("success", True)

    async def kv_list(
        self,
        pattern: str = "*",
        return_values: bool = False,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Union[List[str], List[Dict[str, Any]], Dict[str, Any]]:
        headers = self._get_auth_headers()
        payload: Dict[str, Any] = {"pattern": pattern, "returnValues": return_values}
        if limit is not None:
            payload["limit"] = int(limit)
        if cursor is not None:
            payload["cursor"] = cursor
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/list",
            headers=headers,
            json_body=payload,
        )
        if "items" in data and (limit is not None or cursor is not None):
            return data
        if return_values:
            return data.get("items") or data.get("pairs") or data.get("kvpairs") or []
        return data.get("keys", [])

    async def kv_add(self, key: str, value: Any) -> Any:
        key = validate_string(key)
        headers = self._get_auth_headers()
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/add",
            headers=headers,
            json_body={"key": key, "value": value},
        )
        return data.get("value", data.get("result", data))

    async def kv_incr(self, key: str, value: Any) -> Any:
        key = validate_string(key)
        headers = self._get_auth_headers()
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/incr",
            headers=headers,
            json_body={"key": key, "value": value},
        )
        return data.get("value", data.get("result", data))

    async def kv_decr(self, key: str, value: Any) -> Any:
        key = validate_string(key)
        headers = self._get_auth_headers()
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/decr",
            headers=headers,
            json_body={"key": key, "value": value},
        )
        return data.get("value", data.get("result", data))

    async def kv_update(self, key: str, value: Any) -> Any:
        key = validate_string(key)
        headers = self._get_auth_headers()
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/update",
            headers=headers,
            json_body={"key": key, "value": value},
        )
        return data.get("value", data.get("result", data))

    async def kv_remove(self, key: str, *paths: str) -> Any:
        key = validate_string(key)
        cleaned_paths = [validate_string(p) for p in paths if p is not None]
        headers = self._get_auth_headers()
        data = await self._request_json(
            "POST",
            f"{self.api_base}/kv/remove",
            headers=headers,
            json_body={"key": key, "paths": cleaned_paths},
        )
        return data.get("value", data.get("result", data))

    async def kv_expire(self, key: str, seconds: Union[int, float]) -> Dict[str, Any]:
        key = validate_string(key)
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/kv/expire",
            headers=headers,
            json_body={"key": key, "seconds": seconds},
        )

    async def kv_expire_at(self, key: str, timestamp: Union[int, float, str, datetime]) -> Dict[str, Any]:
        key = validate_string(key)
        if isinstance(timestamp, datetime):
            ts_value: Any = timestamp.isoformat()
        else:
            ts_value = timestamp
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/kv/expireAt",
            headers=headers,
            json_body={"key": key, "timestamp": ts_value},
        )

    async def kv_flush(self, pattern: str = "*") -> Dict[str, Any]:
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/kv/flush",
            headers=headers,
            json_body={"pattern": pattern},
        )

    async def ai_chat(
        self,
        prompt: Optional[Union[str, List[Dict[str, Any]]]] = None,
        options: Optional[Dict[str, Any]] = None,
        test_mode: bool = False,
        image_url: Optional[Union[str, List[str]]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        retry_count: int = 0,
        strict_model: bool = False,
    ) -> Union[Dict[str, Any], AsyncGenerator[Tuple[str, str], None]]:
        """
        AI chat completion, supporting multiple models with fallback and retries.
        """
        if options is None:
            options = {}
        model = options.get("model", self.fallback_models[0])
        driver = self.model_to_driver.get(model, "openai-completion")
        stream = options.get("stream", False)

        temperature = options.get("temperature", 0.7)
        if model in self.force_temperature_1_models:
            if temperature != 1:
                logger.info(f"Overriding temperature to 1 for model '{model}'")
            temperature = 1
        max_tokens = options.get("max_tokens", 1000)

        if messages is None:
            messages = []
            if prompt:
                content = prompt
                if image_url:
                    if not isinstance(image_url, list):
                        image_url = [image_url]
                    content_parts = (
                        [{"type": "text", "text": content}] if isinstance(content, str) else content
                    )
                    for url in image_url:
                        if isinstance(url, str) and url.startswith(("http://", "https://")):
                            safe_url = validate_url(url)
                            content_parts.append({"type": "image_url", "image_url": {"url": safe_url}})
                        else:
                            content_parts.append({"type": "file", "puter_path": str(url)})
                    content = content_parts
                messages.append({"role": "user", "content": content})

        args = {
            "messages": messages,
            "model": model,
            "stream": stream,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "tools": options.get("tools"),
            "testMode": test_mode,
        }
        reserved_keys = {"model", "stream", "max_tokens", "temperature", "tools"}
        for k, v in options.items():
            if k in reserved_keys:
                continue
            if v is None:
                continue
            args[k] = v

        def check_used_model(data: Dict[str, Any], requested_model: str, strict: bool) -> str:
            used_model = None
            if "result" in data and "usage" in data["result"] and data["result"]["usage"]:
                usage = data["result"]["usage"]
                if isinstance(usage, list) and len(usage) > 0:
                    used_model = usage[0].get("model", "unknown")
                elif isinstance(usage, dict):
                    used_model = usage.get("model", data["result"].get("model", "unknown"))
                else:
                    used_model = data["result"].get("model", "unknown")
            elif "metadata" in data and "service_used" in data["metadata"]:
                used_model = data["metadata"].get("service_used", "unknown")

            if used_model and used_model != requested_model:
                msg = f"Requested model {requested_model}, but server used {used_model}"
                if strict:
                    raise ValueError(msg)
                else:
                    logger.warning(msg)
            return used_model or requested_model

        def process_line(
            line: bytes, requested_model: str, strict: bool
        ) -> Optional[Tuple[str, str]]:
            if not line:
                return None
            logger.debug(f"Raw stream line: {line}")
            try:
                data = json.loads(line)
                if not data.get("success", True):
                    error_data = data.get("error", {})
                    error_msg = error_data.get("message", "Unknown error")
                    raise ValueError(f"API error: {error_msg} (code: {error_data.get('code')})")

                used_model = check_used_model(data, requested_model, strict)

                # Custom text format
                if "type" in data and data["type"] == "text" and "text" in data:
                    content = data["text"]
                    if content:
                        return content, used_model

                # Claude-style
                if "result" in data and "message" in data["result"]:
                    msg_content = data["result"]["message"].get("content", "")
                    if isinstance(msg_content, str):
                        return msg_content, used_model
                    elif isinstance(msg_content, list):
                        content = msg_content[0].get("text", "")
                        if content:
                            return content, used_model

                # OpenAI-style
                if "choices" in data:
                    content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if content:
                        return content, used_model

            except json.JSONDecodeError:
                if line.startswith(b"data: "):
                    try:
                        data = json.loads(line[6:])
                        if not data.get("success", True):
                            raise ValueError(f"API error: {data.get('message')}")
                        used_model = check_used_model(data, requested_model, strict)
                        content = data.get("text", "")
                        if content:
                            return content, used_model
                    except json.JSONDecodeError:
                        pass
                else:
                    decoded = line.decode("utf-8", errors="ignore")
                    if decoded.strip():
                        return decoded, requested_model
            return None

        try:
            logger.info(f"Sending ai_chat request: model={model}, stream={stream}")

            async def handle_error(error_msg, error_code=None):
                is_forbidden = error_code in ("no_implementation_available", "forbidden")
                if is_forbidden and retry_count < self.max_retries:
                    if strict_model:
                        raise ValueError(f"Model {model} unavailable (strict mode).")

                    if not test_mode:
                        logger.warning(f"Retrying {model} with test_mode=True")
                        return await self.ai_chat(
                            prompt=prompt,
                            options=options,
                            test_mode=True,
                            image_url=image_url,
                            messages=messages,
                            retry_count=retry_count + 1,
                            strict_model=strict_model,
                        )

                    # Fallback
                    if model in self.fallback_models:
                        idx = self.fallback_models.index(model)
                        next_idx = idx + 1
                    else:
                        next_idx = 0

                    if next_idx < len(self.fallback_models):
                        next_model = self.fallback_models[next_idx]
                        logger.warning(f"Fallback from {model} to {next_model}")
                        options["model"] = next_model
                        await asyncio.sleep(1)
                        return await self.ai_chat(
                            prompt=prompt,
                            options=options,
                            test_mode=test_mode,
                            image_url=image_url,
                            messages=messages,
                            retry_count=retry_count + 1,
                            strict_model=strict_model,
                        )
                raise ValueError(f"AI chat error: {error_msg}")

            if stream:
                raw_stream = await self.drivers_call(
                    "puter-chat-completion",
                    driver,
                    "complete",
                    args=args,
                    stream=True,
                    test_mode=test_mode,
                )
                if not hasattr(raw_stream, "__aiter__"):
                    raise ValueError("Streaming driver call did not return a generator")

                async def async_generator():
                    buffer = b""
                    async for chunk in raw_stream:
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            processed = process_line(line, model, strict_model)
                            if processed:
                                yield processed
                    tail = buffer.strip()
                    if tail:
                        processed = process_line(tail, model, strict_model)
                        if processed:
                            yield processed

                return async_generator()

            else:
                result = await self.drivers_call(
                    "puter-chat-completion",
                    driver,
                    "complete",
                    args=args,
                    stream=False,
                    test_mode=test_mode,
                )
                if not result.get("success", True):
                    err = result.get("error", {})
                    await handle_error(err.get("message"), err.get("code"))

                used_model = check_used_model(result, model, strict_model)
                return {"response": result, "used_model": used_model}

        except aiohttp.ClientError as e:
            logger.error(f"ai_chat request failed: {e}")
            raise

    async def ai_img2txt(self, image: Union[str, Any], test_mode: bool = False) -> str:
        """
        Image to text (OCR) asynchronously.
        """
        try:
            if isinstance(image, str):
                safe_url = validate_url(image)
                payload = {"image_url": safe_url, "testMode": test_mode}
                headers = self._get_auth_headers()
                data = await self._request_json(
                    "POST",
                    f"{self.api_base}/ai/img2txt",
                    headers=headers,
                    json_body=payload,
                )
                return data.get("text")
            else:
                data = aiohttp.FormData()
                data.add_field("testMode", str(test_mode).lower())
                data.add_field("image", image)
                headers = self._get_auth_headers()
                headers.pop("Content-Type", None)
                parsed = await self._request_json(
                    "POST",
                    f"{self.api_base}/ai/img2txt",
                    headers=headers,
                    data=data,
                )
                return parsed.get("text")
        except aiohttp.ClientError as e:
            logger.warning(f"ai_img2txt error: {e}")
            raise

    async def ai_txt2img(
        self, prompt: str, model: str = "pollinations-image", test_mode: bool = False
    ) -> str:
        """
        Text to image using Puter's driver API asynchronously.
        """
        try:
            data = await self.drivers_call(
                "puter-image-generation",
                model,
                "generate",
                args={"prompt": prompt, "testMode": test_mode},
                test_mode=test_mode,
            )
            if "result" in data and "image_url" in data["result"]:
                return data["result"]["image_url"]
            if "result" in data and isinstance(data["result"], dict):
                return data["result"].get("url") or data["result"].get("data")
            raise ValueError(f"Unexpected response format: {data}")
        except aiohttp.ClientError as e:
            logger.warning(f"ai_txt2img error: {e}")
            raise

    async def ai_txt2speech(self, text: str, options: Optional[Dict[str, Any]] = None) -> bytes:
        """
        Text to speech asynchronously. Returns MP3 bytes.
        """
        if options is None:
            options = {}
        payload = {"text": text, "testMode": options.get("testMode", False)}
        headers = self._get_auth_headers()
        audio = await self._request_bytes(
            "POST",
            f"{self.api_base}/ai/txt2speech",
            headers=headers,
            json_body=payload,
        )
        logger.info("ai_txt2speech request successful")
        return audio

    async def ai_list_models(self, force_refresh: bool = False) -> Dict[str, Any]:
        return await self.get_available_models(force_refresh=force_refresh)

    async def ai_list_model_providers(self, force_refresh: bool = False) -> List[str]:
        models_data = await self.get_available_models(force_refresh=force_refresh)
        providers: set[str] = set()
        for model_item in models_data.get("models", []):
            if isinstance(model_item, dict):
                provider = model_item.get("provider")
                if isinstance(provider, str) and provider:
                    providers.add(provider)
        return sorted(providers)

    async def ai_speech2txt(
        self,
        source: Union[str, Any],
        options: Optional[Dict[str, Any]] = None,
        test_mode: bool = False,
    ) -> Union[str, Dict[str, Any]]:
        if options is None:
            options = {}
        payload: Dict[str, Any] = dict(options)
        payload["testMode"] = payload.get("testMode", test_mode)

        if isinstance(source, str):
            if source.startswith(("http://", "https://", "data:")):
                payload.setdefault("audio", source)
            else:
                payload.setdefault("audio", source)
        else:
            data = aiohttp.FormData()
            data.add_field("testMode", str(payload["testMode"]).lower())
            data.add_field("audio", source)
            headers = self._get_auth_headers()
            headers.pop("Content-Type", None)
            result = await self._request_json(
                "POST",
                f"{self.api_base}/ai/speech2txt",
                headers=headers,
                data=data,
            )
            return result

        headers = self._get_auth_headers()
        result = await self._request_json(
            "POST",
            f"{self.api_base}/ai/speech2txt",
            headers=headers,
            json_body=payload,
        )
        if options.get("response_format") == "text" and "text" in result:
            return str(result["text"])
        if "text" in result and len(result) == 1:
            return str(result["text"])
        return result

    async def ai_speech2speech(
        self,
        source: Union[str, Any],
        options: Optional[Dict[str, Any]] = None,
        test_mode: bool = False,
    ) -> Union[bytes, Dict[str, Any]]:
        if options is None:
            options = {}
        payload: Dict[str, Any] = dict(options)
        payload["testMode"] = payload.get("testMode", test_mode)

        if isinstance(source, str):
            payload.setdefault("audio", source)
            headers = self._get_auth_headers()
            return await self._request_bytes(
                "POST",
                f"{self.api_base}/ai/speech2speech",
                headers=headers,
                json_body=payload,
            )

        data = aiohttp.FormData()
        data.add_field("testMode", str(payload["testMode"]).lower())
        data.add_field("audio", source)
        headers = self._get_auth_headers()
        headers.pop("Content-Type", None)
        audio = await self._request_bytes(
            "POST",
            f"{self.api_base}/ai/speech2speech",
            headers=headers,
            data=data,
        )
        return audio

    async def ai_txt2vid(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
        test_mode: bool = False,
    ) -> Dict[str, Any]:
        if options is None:
            options = {}
        payload: Dict[str, Any] = dict(options)
        payload.setdefault("prompt", prompt)
        payload["testMode"] = payload.get("testMode", test_mode)
        headers = self._get_auth_headers()
        return await self._request_json(
            "POST",
            f"{self.api_base}/ai/txt2vid",
            headers=headers,
            json_body=payload,
        )
