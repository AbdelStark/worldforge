"""Jina AI embedding provider integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

import httpx

from worldforge.models import (
    EmbeddingResult,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    ProviderRequestPolicy,
)

from ._config import ProviderConfigSummary, env_value
from .base import ProviderError, ProviderProfileSpec, RemoteProvider, _field_summary
from .http_utils import request_json_with_policy

JINA_BASE_URL = "https://api.jina.ai"
JINA_DEFAULT_MODEL = "jina-embeddings-v3"


@dataclass(slots=True, frozen=True)
class JinaEmbeddingData:
    """Validated embedding data from a single Jina response item."""

    embedding: tuple[float, ...]
    index: int

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
    ) -> JinaEmbeddingData:
        embedding_raw = payload.get("embedding")
        if not isinstance(embedding_raw, list) or not embedding_raw:
            raise ProviderError(
                f"Provider '{provider_name}' embedding response field 'embedding' "
                "must be a non-empty list of floats."
            )
        if not all(isinstance(v, int | float) for v in embedding_raw):
            raise ProviderError(
                f"Provider '{provider_name}' embedding vector must contain only numeric values."
            )
        index = payload.get("index", 0)
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ProviderError(
                f"Provider '{provider_name}' embedding response field 'index' "
                "must be a non-negative integer."
            )
        return cls(
            embedding=tuple(float(v) for v in embedding_raw),
            index=index,
        )


@dataclass(slots=True, frozen=True)
class JinaEmbeddingResponse:
    """Validated response from the Jina embedding endpoint."""

    data: tuple[JinaEmbeddingData, ...]
    model: str
    total_tokens: int

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
    ) -> JinaEmbeddingResponse:
        data_raw = payload.get("data")
        if not isinstance(data_raw, list) or not data_raw:
            raise ProviderError(
                f"Provider '{provider_name}' embedding response field 'data' "
                "must be a non-empty list."
            )
        data = tuple(
            JinaEmbeddingData.from_payload(item, provider_name=provider_name) for item in data_raw
        )
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ProviderError(
                f"Provider '{provider_name}' embedding response field 'model' "
                "must be a non-empty string."
            )
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            raise ProviderError(
                f"Provider '{provider_name}' embedding response field 'usage' "
                "must be a JSON object."
            )
        total_tokens = usage.get("total_tokens", 0)
        if isinstance(total_tokens, bool) or not isinstance(total_tokens, int) or total_tokens < 0:
            raise ProviderError(
                f"Provider '{provider_name}' embedding response usage.total_tokens "
                "must be a non-negative integer."
            )
        return cls(data=data, model=model.strip(), total_tokens=total_tokens)


class JinaProvider(RemoteProvider):
    """HTTP adapter for Jina AI text embeddings."""

    env_var = "JINA_API_KEY"

    def __init__(
        self,
        name: str = "jina",
        *,
        base_url: str = JINA_BASE_URL,
        timeout_seconds: float = 30.0,
        request_policy: ProviderRequestPolicy | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_request_policy = request_policy or ProviderRequestPolicy.remote_defaults(
            request_timeout_seconds=timeout_seconds
        )
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(
                predict=False,
                generate=False,
                reason=False,
                embed=True,
                plan=False,
                transfer=False,
            ),
            profile=ProviderProfileSpec(
                description="Jina AI adapter for text embeddings.",
                implementation_status="scaffold",
                supported_modalities=("text",),
                artifact_types=("embedding",),
                notes=(
                    "Targets the Jina AI /v1/embeddings API.",
                    "Requires a valid JINA_API_KEY.",
                    "Uses jina-embeddings-v3 as the default embedding model.",
                ),
                default_model=JINA_DEFAULT_MODEL,
                supported_models=(
                    "jina-embeddings-v3",
                    "jina-embeddings-v2-base-en",
                    "jina-embeddings-v2-small-en",
                ),
                required_env_vars=("JINA_API_KEY",),
            ),
            request_policy=resolved_request_policy,
            event_handler=event_handler,
        )
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def configured(self) -> bool:
        return bool(env_value(self.env_var))

    def config_summary(self) -> ProviderConfigSummary:
        api_key_from_env = env_value(self.env_var) is not None
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=(
                _field_summary(
                    "JINA_API_KEY",
                    required=True,
                    secret=True,
                    source="env:JINA_API_KEY" if api_key_from_env else "unset",
                    present=api_key_from_env,
                ),
            ),
        )

    def _headers(self) -> dict[str, str]:
        api_key = env_value(self.env_var)
        if not api_key:
            raise ProviderError(f"Provider '{self.name}' is unavailable: missing {self.env_var}.")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            headers=self._headers(),
            transport=self._transport,
        )

    def health(self) -> ProviderHealth:
        started = perf_counter()
        if not self.configured():
            return self._health(started, f"missing {self.env_var}", healthy=False)
        try:
            request_policy = self._require_request_policy()
            with self._client() as client:
                payload = request_json_with_policy(
                    client,
                    method="POST",
                    url="/v1/embeddings",
                    provider_name=self.name,
                    operation_name="healthcheck",
                    policy=request_policy.health,
                    emit_event=self._emit_event,
                    json={"input": "health", "model": JINA_DEFAULT_MODEL},
                )
            JinaEmbeddingResponse.from_payload(payload, provider_name=self.name)
            details = "reachable"
            healthy = True
        except ProviderError as exc:
            healthy = False
            details = str(exc)
        return self._health(started, details, healthy=healthy)

    def embed(self, *, text: str) -> EmbeddingResult:
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(f"Provider '{self.name}' embed() text must be a non-empty string.")
        started = perf_counter()
        self._require_credentials()
        request_policy = self._require_request_policy()
        body: dict[str, object] = {
            "input": text.strip(),
            "model": JINA_DEFAULT_MODEL,
        }
        with self._client() as client:
            payload = request_json_with_policy(
                client,
                method="POST",
                url="/v1/embeddings",
                provider_name=self.name,
                operation_name="embed request",
                policy=request_policy.request,
                emit_event=self._emit_event,
                json=body,
            )
        response = JinaEmbeddingResponse.from_payload(payload, provider_name=self.name)
        if not response.data:
            raise ProviderError(f"Provider '{self.name}' embedding response contained no data.")
        vector = list(response.data[0].embedding)
        latency_ms = max(0.1, (perf_counter() - started) * 1000)
        self._emit_operation_event(
            operation="embed",
            phase="success",
            duration_ms=latency_ms,
            metadata={
                "model": response.model,
                "dimensions": len(vector),
                "total_tokens": response.total_tokens,
            },
        )
        return EmbeddingResult(
            provider=self.name,
            model=response.model,
            vector=vector,
        )
