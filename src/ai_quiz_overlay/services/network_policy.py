"""Central allow-list for user-visible network destinations."""

from __future__ import annotations


OFFICIAL_API_ORIGIN = "https://api.deepseek.com"
OFFICIAL_API_HOST = "api.deepseek.com"

MODEL_SOURCE_DOMAINS = {
    "hf_mirror": (
        "hf-mirror.com",
        "cas-bridge.xethub.hf.co",
    ),
    "github_release": (
        "api.github.com",
        "release-assets.githubusercontent.com",
    ),
}

ALLOWED_MODEL_DOMAINS = frozenset(
    domain
    for domains in MODEL_SOURCE_DOMAINS.values()
    for domain in domains
)
