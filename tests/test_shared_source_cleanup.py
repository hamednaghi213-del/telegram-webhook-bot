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


def test_standalone_source_domain_next_to_source_handle_is_removed():
    source = (
        "پزشکیان: کشور ما قربانی ترور است\n\n"
        "🔷 متن واقعی خبر.\n\n"
        "asriran.com\n"
        "@MyAsriran"
    )
    cleaned = remove_source_signature(
        source,
        source_title="عصر ایران",
        source_username="MyAsriran",
    )
    assert "متن واقعی خبر" in cleaned
    assert "asriran.com" not in cleaned
    assert "@MyAsriran" not in cleaned


def test_domain_in_body_is_preserved_when_not_part_of_source_footer():
    source = (
        "برای مشاهده سند به example.com مراجعه کنید.\n\n"
        "این نشانی بخشی از متن واقعی خبر است."
    )
    assert remove_source_signature(
        source,
        source_title="عصر ایران",
        source_username="MyAsriran",
    ) == source
