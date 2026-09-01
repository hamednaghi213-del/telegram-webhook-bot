from core.formatter import remove_source_signature
from core.publication_icons import format_with_profile
from core.webhook_handler import prepare_text_content


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


def test_trailing_forward_source_url_is_removed_without_handle():
    source = (
        "WSJ: Trump Rejects Initial Iran Deal, Hikes Pressure\n\n"
        "Trump is abandoning the June understanding with Iran.\n\n"
        "https://www.c14news.com/article/1495422/"
    )

    cleaned = remove_source_signature(
        source,
        source_title="Channel 14 - English Edition",
        source_username="C14English",
    )

    assert cleaned == (
        "WSJ: Trump Rejects Initial Iran Deal, Hikes Pressure\n\n"
        "Trump is abandoning the June understanding with Iran."
    )


def test_body_url_is_preserved_for_forwarded_content():
    source = (
        "برای جزئیات https://example.com/report را در متن خبر ببینید.\n\n"
        "ادامه متن اصلی خبر"
    )

    cleaned = remove_source_signature(
        source,
        source_title="Example News",
        source_username="ExampleNews",
    )

    assert "https://example.com/report" in cleaned


def test_url_only_forward_is_not_emptied_as_source_footer():
    source = "https://example.com/report"

    cleaned = remove_source_signature(
        source,
        source_title="Example News",
        source_username="ExampleNews",
    )

    assert cleaned == source


def test_workspace_neutral_text_reuses_legacy_cleanup_output():
    source = (
        "محسن رضایی: ایران فهرستی از شروط خود را آماده کرده!!\n\n"
        "ایران در حال حاضر یک مسیر موقت و مشخص دارد.\n\n"
        "#N\n"
        "🔷 @mahdaviatakhbar 🔷"
    )
    prepared = prepare_text_content(
        source,
        [],
        forward_source={
            "is_forwarded": True,
            "source_title": "صائب بن مالک",
            # Deliberately differs from the footer handle: Legacy cleanup must
            # still remove foreign branding before Workspace formatting.
            "source_username": "SaebNews",
        },
    )

    assert prepared["neutral_text"] == prepared["main_text"]
    assert "#N" not in prepared["neutral_text"]
    assert "@mahdaviatakhbar" not in prepared["neutral_text"]

    workspace_output = format_with_profile(
        prepared["neutral_text"],
        {"title_icon": "❇️", "body_icons": ["🔷"]},
    )
    assert "#N" not in workspace_output
    assert "@mahdaviatakhbar" not in workspace_output


def test_trailing_source_icons_after_last_real_word_are_removed():
    source = (
        "قدردانی رئیس‌جمهور از پیام مقام معظم رهبری "
        "به مناسبت هفته دولت ✳️\n\n"
        "🔷 هم‌میهن را در فضای مجازی دنبال کنید:\n\n"
        "🔷 سایت - بله - تلگرام - روبیکا - اینستاگرام"
    )

    cleaned = remove_source_signature(
        source,
        source_title="هم‌میهن",
        source_username="hammihanonline",
    )

    assert cleaned == (
        "قدردانی رئیس‌جمهور از پیام مقام معظم رهبری "
        "به مناسبت هفته دولت"
    )
    assert "✳️" not in cleaned

def test_decorated_source_handle_and_adjacent_short_hashtag_are_removed():
    source = (
        "فوری | صدای چندین انفجار در تنگه هرمز شنیده شد "
        "که ناشی از شلیک موشک توسط نیروی دریایی سپاه "
        "پاسداران به سمت کشتی‌های متخلف بود\n\n"
        "#P\n"
        "🔷 @mahdaviatakhbar 🔷"
    )

    cleaned = remove_source_signature(
        source,
        source_title="منبع آزمایشی",
        source_username="DifferentSource",
    )

    assert cleaned == (
        "فوری | صدای چندین انفجار در تنگه هرمز شنیده شد "
        "که ناشی از شلیک موشک توسط نیروی دریایی سپاه "
        "پاسداران به سمت کشتی‌های متخلف بود"
    )
    assert "#P" not in cleaned
    assert "@mahdaviatakhbar" not in cleaned

def test_adjacent_source_media_label_is_removed_with_real_forward_metadata():
    source = (
        "وال استریت ژورنال گزارش داد:\n\n"
        "دن دریسکول، وزیر نیروی زمینی ایالات متحده، استعفای خود را ارائه کرد.\n\n"
        "سپاه سایبری پاسداران 👇🏻\n"
        "@SEPAHCYBERY"
    )

    cleaned = remove_source_signature(
        source,
        source_title="سپاه سایبری پاسداران IRGC 🏴",
        source_username="sepahcybery",
    )

    assert "سپاه سایبری پاسداران" not in cleaned
    assert "@SEPAHCYBERY" not in cleaned
    assert "وال استریت ژورنال گزارش داد:" in cleaned
    assert "دن دریسکول، وزیر نیروی زمینی ایالات متحده، استعفای خود را ارائه کرد." in cleaned
