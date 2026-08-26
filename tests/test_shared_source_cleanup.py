from core.formatter import remove_source_signature


def test_requested_source_footer_is_removed_without_touching_body_entities():
    source = (
        "متن اصلی خبر با @real_mention و #هاشتگ_واقعی\n\n"
        "🔷 #N\n"
        "🔷 @mahdaviatakhbar"
    )
    cleaned = remove_source_signature(source, source_username="mahdaviatakhbar")
    assert cleaned == "متن اصلی خبر با @real_mention و #هاشتگ_واقعی"

