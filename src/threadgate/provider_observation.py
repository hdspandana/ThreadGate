"""Request-local provider observations; never collect prompts, outputs or secrets."""
from contextlib import contextmanager
from contextvars import ContextVar

_EVENTS=ContextVar('threadgate_provider_events',default=None)


@contextmanager
def capture():
    events=[]
    token=_EVENTS.set(events)
    try:yield events
    finally:_EVENTS.reset(token)


def error_kind(exc):
    seen = set()

    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        name = type(exc).__name__.lower()

        code = getattr(exc, "code", None)
        if code is None:
            code = getattr(exc, "status_code", None)

        try:
            code = int(code)
        except (TypeError, ValueError):
            code = None

        if code == 429:
            return "rate_limit"
        if code in {401, 403}:
            return "authentication"
        if code is not None and 400 <= code < 500:
            return "client_error"

        if "timeout" in name or "deadline" in name:
            return "timeout"
        if "validationerror" in name or "jsondecode" in name:
            return "schema"
        if "API_KEY is not set" in str(exc):
            return "missing_key"

        exc = exc.__cause__ or exc.__context__

    return "provider"


def observe(attempt,status,elapsed_ms,response=None,error=None):
    events=_EVENTS.get()
    if events is None:return
    item={'attempt':attempt,'status':status,'elapsed_ms':round(elapsed_ms,2)}
    if error is not None:item['error_kind']=error_kind(error)
    metadata=getattr(response,'usage_metadata',None)
    for name in ['prompt_token_count','candidates_token_count','total_token_count','cached_content_token_count']:
        value=metadata.get(name) if isinstance(metadata,dict) else getattr(metadata,name,None)
        if isinstance(value,int) and not isinstance(value,bool) and value>=0:item[name]=value
    events.append(item)
