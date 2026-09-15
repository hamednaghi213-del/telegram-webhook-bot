from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple


logger = logging.getLogger(__name__)


# =========================================================
# UNIVERSAL TRANSLATION PROVIDER REGISTRY
# =========================================================
#
# این ماژول هیچ وابستگی به Telegram / Bale / Workspace ندارد.
#
# وظیفه:
#
# Translation Engine
#        ↓
# Provider Registry
#        ↓
# Primary Provider
#        ↓ failure
# Fallback Provider
#        ↓ failure
# Next Provider
#        ↓
# Fail Closed
#
# زبان ورودی برای Registry اهمیتی ندارد.
# تمام زبان‌ها از یک مسیر مشترک عبور می‌کنند.
#
# Providerها فقط مسئول تولید ترجمه هستند.
# تشخیص زبان، Review، Publication و Branding در لایه‌های
# موجود پروژه باقی می‌مانند.
#
# =========================================================


TranslationProvider = Callable[..., str]


# =========================================================
# PROVIDER ENTRY
# =========================================================


@dataclass(frozen=True)
class TranslationProviderEntry:
    """
    یک Provider ثبت‌شده در زنجیره ترجمه.

    priority:
        عدد کمتر = اولویت بیشتر

    enabled:
        امکان غیرفعال کردن Provider بدون حذف آن از Registry
    """

    name: str
    provider: TranslationProvider
    priority: int = 100
    enabled: bool = True


# =========================================================
# REGISTRY
# =========================================================


class TranslationProviderRegistry:
    """
    Registry عمومی Providerهای ترجمه.

    ویژگی‌ها:
    - مستقل از زبان
    - مستقل از Publication Engine
    - پشتیبانی از چند Provider
    - ترتیب deterministic
    - جلوگیری از ثبت تکراری Provider
    - امکان Primary / Fallback chain
    """

    def __init__(self) -> None:
        self._providers: Dict[
            str,
            TranslationProviderEntry,
        ] = {}

    # -----------------------------------------------------
    # REGISTER
    # -----------------------------------------------------

    def register(
        self,
        *,
        name: str,
        provider: TranslationProvider,
        priority: int = 100,
        enabled: bool = True,
        replace: bool = False,
    ) -> None:
        provider_name = str(
            name or ""
        ).strip().lower()

        if not provider_name:
            raise ValueError(
                "translation_provider_name_required"
            )

        if not callable(provider):
            raise TypeError(
                "translation_provider_must_be_callable"
            )

        if (
            provider_name in self._providers
            and not replace
        ):
            raise ValueError(
                "translation_provider_already_registered"
            )

        entry = TranslationProviderEntry(
            name=provider_name,
            provider=provider,
            priority=int(priority),
            enabled=bool(enabled),
        )

        self._providers[
            provider_name
        ] = entry

        logger.info(
            "🌐 Translation provider registered | "
            "provider=%s | priority=%s | enabled=%s",
            provider_name,
            entry.priority,
            entry.enabled,
        )

    # -----------------------------------------------------
    # UNREGISTER
    # -----------------------------------------------------

    def unregister(
        self,
        name: str,
    ) -> None:
        provider_name = str(
            name or ""
        ).strip().lower()

        if not provider_name:
            return

        self._providers.pop(
            provider_name,
            None,
        )

    # -----------------------------------------------------
    # CLEAR
    # -----------------------------------------------------

    def clear(self) -> None:
        self._providers.clear()

    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    def get(
        self,
        name: str,
    ) -> Optional[TranslationProviderEntry]:
        provider_name = str(
            name or ""
        ).strip().lower()

        if not provider_name:
            return None

        return self._providers.get(
            provider_name
        )

    # -----------------------------------------------------
    # ENABLED PROVIDERS
    # -----------------------------------------------------

    def enabled_entries(
        self,
    ) -> Tuple[
        TranslationProviderEntry,
        ...,
    ]:
        entries = [
            entry
            for entry in self._providers.values()
            if entry.enabled
        ]

        entries.sort(
            key=lambda item: (
                item.priority,
                item.name,
            )
        )

        return tuple(
            entries
        )

    # -----------------------------------------------------
    # PROVIDER FUNCTIONS
    # -----------------------------------------------------

    def enabled_providers(
        self,
    ) -> Tuple[
        TranslationProvider,
        ...,
    ]:
        return tuple(
            entry.provider
            for entry in self.enabled_entries()
        )

    # -----------------------------------------------------
    # NAMES
    # -----------------------------------------------------

    def enabled_names(
        self,
    ) -> Tuple[
        str,
        ...,
    ]:
        return tuple(
            entry.name
            for entry in self.enabled_entries()
        )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    def has_enabled_provider(
        self,
    ) -> bool:
        return bool(
            self.enabled_entries()
        )

    def count(
        self,
    ) -> int:
        return len(
            self._providers
        )

    def enabled_count(
        self,
    ) -> int:
        return len(
            self.enabled_entries()
        )

    # -----------------------------------------------------
    # DESCRIBE
    # -----------------------------------------------------

    def describe(
        self,
    ) -> List[Dict[str, object]]:
        return [
            {
                "name": entry.name,
                "priority": entry.priority,
                "enabled": entry.enabled,
            }
            for entry in sorted(
                self._providers.values(),
                key=lambda item: (
                    item.priority,
                    item.name,
                ),
            )
        ]


# =========================================================
# GLOBAL REGISTRY
# =========================================================


_registry = TranslationProviderRegistry()


# =========================================================
# PUBLIC API
# =========================================================


def get_translation_provider_registry(
) -> TranslationProviderRegistry:
    """
    Registry مشترک کل Translation Engine.
    """

    return _registry


def register_translation_provider(
    *,
    name: str,
    provider: TranslationProvider,
    priority: int = 100,
    enabled: bool = True,
    replace: bool = False,
) -> None:
    """
    ثبت Provider در Registry مشترک.
    """

    _registry.register(
        name=name,
        provider=provider,
        priority=priority,
        enabled=enabled,
        replace=replace,
    )


def unregister_translation_provider(
    name: str,
) -> None:
    _registry.unregister(
        name
    )


def get_registered_translation_provider(
    name: str,
) -> Optional[TranslationProviderEntry]:
    return _registry.get(
        name
    )


def get_translation_provider_entries(
) -> Tuple[
    TranslationProviderEntry,
    ...,
]:
    """
    زنجیره فعال Providerها به ترتیب اولویت.
    """

    return (
        _registry.enabled_entries()
    )


def get_translation_provider_chain(
) -> Tuple[
    TranslationProvider,
    ...,
]:
    """
    فقط Callableهای Providerها به ترتیب اجرا.
    """

    return (
        _registry.enabled_providers()
    )


def get_translation_provider_names(
) -> Tuple[
    str,
    ...,
]:
    return (
        _registry.enabled_names()
    )


def translation_provider_registry_ready(
) -> bool:
    return (
        _registry.has_enabled_provider()
    )


def describe_translation_provider_registry(
) -> List[
    Dict[str, object]
]:
    """
    اطلاعات غیرحساس برای Health/Debug.

    هیچ API Key یا Secret در خروجی وجود ندارد.
    """

    return (
        _registry.describe()
    )


# =========================================================
# TEST / CONTROL HELPERS
# =========================================================


def reset_translation_provider_registry(
) -> None:
    """
    برای تست‌ها و initialization کنترل‌شده.

    در Runtime عادی نباید بی‌دلیل فراخوانی شود.
    """

    _registry.clear()


def configure_translation_provider_registry(
    providers: Iterable[
        TranslationProviderEntry
    ],
) -> None:
    """
    جایگزینی کنترل‌شده Registry.

    کاربرد اصلی:
    - bootstrap
    - tests
    - dependency injection
    """

    _registry.clear()

    for entry in providers:
        _registry.register(
            name=entry.name,
            provider=entry.provider,
            priority=entry.priority,
            enabled=entry.enabled,
        )
