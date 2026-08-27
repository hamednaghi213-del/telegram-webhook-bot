from core.formatter import remove_source_signature


def test_requested_source_footer_is_removed_without_touching_body_entities():
    source = (
        "متن اصلی خبر با @real_mention و #هاشتگ_واقعی\n\n"
        "🔷 #N\n"
        "🔷 @mahdaviatakhbar"
    )
    cleaned = remove_source_signature(source, source_username="mahdaviatakhbar")
    assert cleaned == "متن اصلی خبر با @real_mention و #هاشتگ_واقعی"


def test_linked_promotional_source_label_is_removed_before_body_formatting():
    source = (
        "اکسیوس به نقل از منبع مطلع:\n"
        "امروز ویتکاف و کوشنر بازدید می‌کنند.\n\n"
        "🔷 یک منبع مطلع گفت: انتظار می‌رود مذاکرات ادامه یابد.\n\n"
        "🔷 کانال تحلیلی مالی دیپارتمان ZTE"
    )
    cleaned = remove_source_signature(
        source,
        source_title="💱 دیپارتمان ZTE13 💱",
        source_username="ZTE13",
    )
    assert "یک منبع مطلع گفت" in cleaned
    assert "کانال تحلیلی مالی دیپارتمان ZTE" not in cleaned
    assert cleaned.endswith("مذاکرات ادامه یابد.")


def test_body_sentence_that_mentions_source_title_is_preserved():
    source = (
        "متن اصلی خبر\n\n"
        "بر اساس گزارش دیپارتمان ZTE، بازار امروز تغییر کرد."
    )
    cleaned = remove_source_signature(
        source,
        source_title="دیپارتمان ZTE13",
        source_username="ZTE13",
    )
    assert cleaned == source
