"""Chat Completions compatible HTTP adapter. No task or environment access."""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from ..interface import Reply, ProtocolError, ModelHTTPError


def _safe_diagnostic(value, secret=None, limit=512):
    """Bound provider diagnostics and strip credentials, URLs and image payloads."""
    if not isinstance(value, str):
        return ""
    if secret:
        value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"data:[^\s\"']+", "[IMAGE REDACTED]", value, flags=re.I)
    value = re.sub(r"https?://[^\s\"']+", "[URL REDACTED]", value, flags=re.I)
    value = re.sub(r"Bearer\s+[^\s,;\"']+", "Bearer [REDACTED]", value, flags=re.I)
    value = re.sub(r"(api[_-]?key|token|authorization|password)([\"']?\s*[:=]\s*[\"']?)[^\s,;\"']+", r"\1\2[REDACTED]", value, flags=re.I)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    return " ".join(value.split())[:limit]


class ChatModel:
    def __init__(self, config):
        self.config = config
        self._recovered_output_limit = None
        self.endpoint = config["endpoint"]
        if not self.endpoint.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            raise ValueError("Model endpoint must use HTTPS, except local development endpoints")
        if not config.get("model") or config["model"] == "SET_MODEL_NAME":
            raise ValueError("Configure the model name first")

    def generate(self, messages, tools, timeout):
        cfg = self.config
        headers = {"Content-Type": "application/json"}
        key = None
        key_env = cfg.get("api_key_env")
        if key_env:
            key = os.environ.get(key_env)
            if not key:
                raise ValueError(f"Missing API key environment variable: {key_env}")
            headers["Authorization"] = "Bearer " + key
        parameters = dict(cfg.get("parameters", {}))
        token_parameter = next((name for name in ("max_completion_tokens", "max_tokens") if name in parameters), None)
        if token_parameter and self._recovered_output_limit is not None:
            parameters[token_parameter] = max(parameters[token_parameter], self._recovered_output_limit)
        if set(parameters) & {"messages", "tools", "model", "stream"}:
            raise ValueError("Model parameters override reserved fields")
        payload = {**parameters, "model": cfg["model"], "messages": messages,
                   "tools": tools, "tool_choice": "required", "parallel_tool_calls": False}
        body = json.dumps(payload).encode()
        started = time.monotonic()
        self.last_request_metrics = {"payload_bytes": len(body), "payload_sha256": hashlib.sha256(body).hexdigest(), "timeout_seconds": timeout}
        if token_parameter:
            self.last_request_metrics["output_token_limit"] = parameters[token_parameter]
        req = urllib.request.Request(self.endpoint, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                self.last_request_metrics["headers_seconds"] = round(time.monotonic() - started, 3)
                result = json.load(response)
                status = getattr(response, "status", None)
                self.last_request_metrics["http_status"] = status if isinstance(status, int) else None
                details = (result.get("usage") or {}).get("completion_tokens_details") or {}
                if isinstance(details.get("reasoning_tokens"), int):
                    self.last_request_metrics["reasoning_tokens"] = details["reasoning_tokens"]
        except urllib.error.HTTPError as exc:
            self.last_request_metrics["http_status"] = exc.code
            safe_codes = {"context_length_exceeded", "invalid_request_error", "invalid_api_key",
                          "rate_limit_exceeded", "insufficient_quota", "model_not_found",
                          "unsupported_parameter", "content_policy_violation", "server_error"}
            code = "unspecified"
            message = ""
            request_id = ""
            for name in ("x-request-id", "x-tt-logid", "request-id"):
                value = exc.headers.get(name) if exc.headers else None
                # HTTPMessage is case-insensitive; support simple test mappings too.
                if not value and exc.headers:
                    value = next((v for k, v in exc.headers.items() if k.lower() == name), None)
                if value:
                    request_id = _safe_diagnostic(value, key, 128)
                    break
            try:
                error = json.loads(exc.read(65536)).get("error", {})
                if isinstance(error, dict):
                    message = _safe_diagnostic(error.get("message"), key)
                for value in (error.get("code"), error.get("type")):
                    if isinstance(value, str) and (value in safe_codes or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", value)) and value != key:
                        code = value
                        break
                limit = re.search(r"Image count (\d{1,6}) exceeds limit (\d{1,6}) per request", str(error.get("message", "")))
                if limit:
                    code = "image_count_exceeded"
                    self.last_request_metrics.update(provider_image_count=int(limit[1]), provider_image_limit=int(limit[2]))
            except (ValueError, AttributeError, OSError):
                pass
            finally:
                exc.close()
            self.last_request_metrics.update(provider_code=code, provider_message=message, request_id=request_id)
            failure = ModelHTTPError(exc.code, code, message, request_id)
            failure.retryable = False
            if (cfg.get("retry_image_parsing_errors", True) and exc.code == 400
                    and code == "InvalidParameter" and re.fullmatch(
                        r"image input format/parsing error(?: Request id: [A-Za-z0-9_-]+)?[.]?", message)):
                failure.retryable = True
            raise failure from None
        finally:
            elapsed = time.monotonic() - started
            self.last_request_metrics["elapsed_seconds"] = round(elapsed, 3)
            if "headers_seconds" in self.last_request_metrics:
                self.last_request_metrics["body_seconds"] = round(max(0, elapsed - self.last_request_metrics["headers_seconds"]), 3)
        usage = result.get('usage', {}) if isinstance(result, dict) else {}
        usage = usage if isinstance(usage, dict) else {}
        try:
            message = result["choices"][0]["message"]
            if not isinstance(message, dict): raise TypeError()
        except (KeyError, IndexError, TypeError):
            raise ProtocolError("Malformed model response", usage) from None
        calls = message.get("tool_calls", [])
        if not calls:
            reason = result["choices"][0].get("finish_reason", "unknown")
            reason = reason if reason in {"stop", "length", "tool_calls", "content_filter"} else "unknown"
            # The runner owns retries and usage accounting. Increase only the next
            # request's explicit output budget; never issue hidden HTTP calls here.
            if reason == "length" and token_parameter:
                current_limit = parameters[token_parameter]
                ceiling = cfg.get("truncation_max_tokens", current_limit)
                if (isinstance(current_limit, int) and not isinstance(current_limit, bool)
                        and isinstance(ceiling, int) and not isinstance(ceiling, bool)
                        and 0 < current_limit < ceiling):
                    self._recovered_output_limit = ceiling
            count = result.get("usage", {}).get("completion_tokens")
            count = count if isinstance(count, int) else "unknown"
            raise ProtocolError(f"Model did not return a structured tool call (finish_reason={reason}, completion_tokens={count})", result.get("usage", {}))
        allowed = {t["function"]["name"] for t in tools}
        actions = []
        for call in calls:
            if not isinstance(call, dict) or not isinstance(call.get('function'), dict):
                raise ProtocolError("Malformed tool call", usage)
            fn = call["function"]
            if not isinstance(fn.get('name'), str) or not isinstance(fn.get('arguments'), str):
                raise ProtocolError("Malformed tool function", usage)
            if fn["name"] not in allowed:
                raise ProtocolError("Model requested an unavailable tool", result.get("usage", {}))
            try:
                args = json.loads(fn["arguments"])
            except (ValueError, TypeError):
                raise ProtocolError("Tool arguments must be valid JSON", result.get("usage", {})) from None
            if not isinstance(args, dict) or "type" in args:
                raise ProtocolError("Invalid action arguments", result.get("usage", {}))
            actions.append({"type": fn["name"], **args})
        text = message.get('content') or ''
        if not isinstance(text,str):raise ProtocolError('Tool response content must be text or null',usage)
        native_calls=[{'id':call.get('id') or 'sgb_'+uuid.uuid4().hex,'type':'function',
                       'function':{'name':call['function']['name'],'arguments':call['function']['arguments']}}
                      for call in calls]
        native={'role':'assistant','content':text or None,'tool_calls':native_calls}
        return Reply(actions, text, usage, native_message=native)
