"""Centralized selectors and page markers for the experimental host."""

from __future__ import annotations


OFFICIAL_WEB_URL = "https://chat.deepseek.com/"
LOGIN_PATH = "/sign_in"
LOGIN_SUCCESS_SELECTORS = (
    "textarea",
    "[contenteditable='true']",
)
