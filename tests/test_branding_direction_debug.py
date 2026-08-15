import sys
import types

from core.media_handler import (
    build_branding_for_user
)


# =========================================================
# DIRECTION CONTROL CHARACTERS
# =========================================================

DIRECTION_MARKS = {
    "LRM": "\u200e",
    "RLM": "\u200f",
    "LRE": "\u202a",
    "RLE": "\u202b",
    "PDF": "\u202c",
    "LRO": "\u202d",
    "RLO": "\u202e",
    "LRI": "\u2066",
    "RLI": "\u2067",
    "FSI": "\u2068",
    "PDI": "\u2069",
}


# =========================================================
# DEBUG TEST
# =========================================================

def test_debug_branding_direction_characters():

    fake_branding = {
        "hashtag": "#دنیا_۲۴_نیوز",
        "channel_tag": "@Donya24News"
    }

    # =====================================================
    # FAKE BRANDING MANAGER
    #
    # ماژول واقعی import نمی‌شود تا وابستگی Database
    # وارد این تست تشخیصی نشود.
    # =====================================================

    fake_branding_module = types.ModuleType(
        "core.branding_manager"
    )

    def fake_get_branding(
        user_id
    ):
        return dict(
            fake_branding
        )

    fake_branding_module.get_branding = (
        fake_get_branding
    )

    old_module = sys.modules.get(
        "core.branding_manager"
    )

    try:

        sys.modules[
            "core.branding_manager"
        ] = fake_branding_module

        branding = (
            build_branding_for_user(
                123456
            )
        )

    finally:

        if old_module is not None:

            sys.modules[
                "core.branding_manager"
            ] = old_module

        else:

            sys.modules.pop(
                "core.branding_manager",
                None
            )

    # =====================================================
    # DEBUG OUTPUT
    # =====================================================

    print()
    print(
        "===================================="
    )
    print(
        "BRANDING DEBUG"
    )
    print(
        "===================================="
    )

    print(
        "REPR:",
        repr(
            branding
        )
    )

    print(
        "UNICODE:",
        [
            f"U+{ord(char):04X}"
            for char in branding
        ]
    )

    for name, character in (
        DIRECTION_MARKS.items()
    ):

        print(
            f"HAS {name}:",
            character in branding
        )

    print(
        "===================================="
    )

    # =====================================================
    # EXPECTED EXACT VALUE
    # =====================================================

    assert (
        branding
        == (
            "#دنیا_۲۴_نیوز\n"
            "@Donya24News"
        )
    )

    # =====================================================
    # NO DIRECTION CONTROL CHARACTERS
    # =====================================================

    for character in (
        DIRECTION_MARKS.values()
    ):

        assert (
            character
            not in branding
        )
