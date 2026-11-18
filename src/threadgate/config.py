"""Shared environment loading. Values and credentials are never printed here."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

PLACEHOLDERS = {'your-key-here','your_key_here','changeme','placeholder','xxxx',''}
SECRET_KEYS = ('GEMINI_API_KEY','GOOGLE_API_KEY','THREADGATE_MODEL','THREADGATE_WORKSPACE_DB','THREADGATE_REQUIRE_MFA')


def is_configured(value: str | None) -> bool:
    return bool(value and value.strip().lower() not in PLACEHOLDERS and not value.strip().startswith('<'))


def load_environment(root: Path, secrets=None):
    # Offline release checks set this before spawning test processes. A local
    # .env must not turn a supposedly offline validation into paid API calls.
    if os.getenv('THREADGATE_SKIP_DOTENV') != '1':
        load_dotenv(root / '.env',override=False)
        if secrets is not None:
            for key in SECRET_KEYS:
                placeholder_key = key in {'GEMINI_API_KEY','GOOGLE_API_KEY'} and not is_configured(os.getenv(key))
                if key in secrets and (not os.environ.get(key) or placeholder_key):
                    os.environ[key] = str(secrets[key])
    for name in ('THREADGATE_WORKSPACE_DB','THREADGATE_DB'):
        if os.getenv(name) and not Path(os.environ[name]).is_absolute():
            os.environ[name] = str(root / os.environ[name])
    for key in ('GEMINI_API_KEY','GOOGLE_API_KEY'):
        if key in os.environ and not is_configured(os.environ[key]):
            os.environ.pop(key)


def key_configured():
    return is_configured(os.getenv('GEMINI_API_KEY')) or is_configured(os.getenv('GOOGLE_API_KEY'))


def check_settings():
    issues = []
    if os.getenv("THREADGATE_REQUIRE_MFA","0").strip().lower() not in {"0","1","true","false"}:
        issues.append("THREADGATE_REQUIRE_MFA must be 0/1 or false/true.")
    for name,default in [('THREADGATE_HTTP_TIMEOUT_MS','30000'),('THREADGATE_TOTAL_BUDGET_MS','90000')]:
        try:
            value = int(os.getenv(name,default))
            if not 100 <= value <= 300000:
                raise ValueError()
        except ValueError:
            issues.append(name+' must be an integer from 100 to 300000 milliseconds.')
    if not os.getenv('THREADGATE_MODEL','gemini-2.5-flash').strip():
        issues.append('THREADGATE_MODEL must not be blank.')
    return issues
