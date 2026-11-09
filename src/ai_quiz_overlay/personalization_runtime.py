"""Runtime defaults and committed personalization asset resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .branding import INTERFACE_NAME, SOFTWARE_NAME, asset_path
from .config import (
    AppConfig,
    PersonalizationConfig,
    get_config_directory,
)


PERSONALIZATION_DIRECTORY_NAME = "personalization"


@dataclass(frozen=True)
class BrandRuntime:
    interface_name: str
    software_name: str
    app_icon_path: Path
    title_logo_path: Path | None
    ball_image_path: Path | None
    background_path: Path | None
    background_mode: str
    background_blur: int
    background_dim: int
    revision: int

    def dialog_title(self, subject: str) -> str:
        return f"{self.software_name} · {subject}"


def personalization_directory() -> Path:
    return get_config_directory() / PERSONALIZATION_DIRECTORY_NAME


def resolve_committed_asset(asset_id: str) -> Path | None:
    if not asset_id:
        return None
    path = personalization_directory() / asset_id
    return path if path.is_file() else None


def runtime_from_config(
    config: AppConfig,
    *,
    revision: int = 0,
) -> BrandRuntime:
    personalization = config.personalization
    app_icon = resolve_committed_asset(
        personalization.app_icon_asset
    )
    return BrandRuntime(
        interface_name=(
            personalization.interface_name or INTERFACE_NAME
        ),
        software_name=(
            personalization.software_name or SOFTWARE_NAME
        ),
        app_icon_path=(
            app_icon or asset_path("brand", "app_icon.ico")
        ),
        title_logo_path=resolve_committed_asset(
            personalization.title_logo_asset
        ),
        ball_image_path=resolve_committed_asset(
            personalization.ball_image_asset
        ),
        background_path=resolve_committed_asset(
            personalization.background_asset
        ),
        background_mode=personalization.background_mode,
        background_blur=personalization.background_blur,
        background_dim=personalization.background_dim,
        revision=revision,
    )


_CURRENT_RUNTIME = runtime_from_config(AppConfig())


def current_brand_runtime() -> BrandRuntime:
    return _CURRENT_RUNTIME


def set_brand_runtime(runtime: BrandRuntime) -> None:
    global _CURRENT_RUNTIME
    _CURRENT_RUNTIME = runtime


def runtime_from_personalization(
    personalization: PersonalizationConfig,
    *,
    asset_directory: Path | None = None,
    revision: int = 0,
) -> BrandRuntime:
    committed_directory = personalization_directory()
    directories = (
        (asset_directory, committed_directory)
        if asset_directory is not None
        and asset_directory != committed_directory
        else (committed_directory,)
    )

    def asset(asset_id: str) -> Path | None:
        if not asset_id:
            return None
        for directory in directories:
            path = directory / asset_id
            if path.is_file():
                return path
        return None

    return BrandRuntime(
        interface_name=personalization.interface_name or INTERFACE_NAME,
        software_name=personalization.software_name or SOFTWARE_NAME,
        app_icon_path=(
            asset(personalization.app_icon_asset)
            or asset_path("brand", "app_icon.ico")
        ),
        title_logo_path=asset(personalization.title_logo_asset),
        ball_image_path=asset(personalization.ball_image_asset),
        background_path=asset(personalization.background_asset),
        background_mode=personalization.background_mode,
        background_blur=personalization.background_blur,
        background_dim=personalization.background_dim,
        revision=revision,
    )
