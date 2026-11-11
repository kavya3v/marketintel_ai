"""Local and Streamlit Cloud settings, without copying secrets into graph state."""
import os
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st

DOTENV_PATH = Path(__file__).resolve().parents[1] / '.env'
SETTING_NAMES = ('TAVILY_API_KEY', 'FIREWORKS_API_KEY', 'FIREWORKS_MODEL')


def get_setting(name):
    """Precedence: Streamlit Secrets > existing environment > project .env."""
    if name not in SETTING_NAMES:
        raise ValueError('Unsupported application setting.')
    try:
        value = st.secrets.get(name)
    except (FileNotFoundError, KeyError):
        value = None  # Local CLI/tests may have no secrets.toml at all.
    if value is None:
        load_dotenv(DOTENV_PATH, override=False)
        value = os.getenv(name, '')
    return value.strip() if isinstance(value, str) else ''


def missing_setting_message(name):
    return (f'Missing {name}. Add it to Streamlit app Settings → Secrets on Community Cloud, '
            'or to the project .env file / environment locally. Save settings and restart the app.')
