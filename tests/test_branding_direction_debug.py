from core.media_handler import build_branding_for_user


def test_debug_branding_direction_characters(monkeypatch):

    fake_branding = {
        "hashtag": "#دنیا_۲۴_نیوز",
        "channel_tag": "@Donya24News"
    }

    import core.branding_manager

    monkeypatch.setattr(
        core.branding_manager,
        "get_branding",
        lambda user_id: fake_branding
    )

    branding = build_branding_for_user(
        123456
    )

    print("\n")
    print("====================================")
    print("BRANDING DEBUG")
    print("====================================")

    print(
        "REPR:",
        repr(branding)
    )

    print(
        "UNICODE:",
        [
            f"U+{ord(char):04X}"
            for char in branding
        ]
    )

    print(
        "HAS RLM:",
        "\u200f" in branding
    )

    print(
        "HAS LRM:",
        "\u200e" in branding
    )

    print(
        "HAS LRE:",
        "\u202a" in branding
    )

    print(
        "HAS RLE:",
        "\u202b" in branding
    )

    print(
        "HAS PDF:",
        "\u202c" in branding
    )

    print(
        "HAS LRO:",
        "\u202d" in branding
    )

    print(
        "HAS RLO:",
        "\u202e" in branding
    )

    print(
        "HAS LRI:",
        "\u2066" in branding
    )

    print(
        "HAS RLI:",
        "\u2067" in branding
    )

    print(
        "HAS FSI:",
        "\u2068" in branding
    )

    print(
        "HAS PDI:",
        "\u2069" in branding
    )

    print("====================================")

    assert branding == (
        "#دنیا_۲۴_نیوز\n"
        "@Donya24News"
    )
