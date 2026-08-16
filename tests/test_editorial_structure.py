from core.editorial_structure import (
    AUTHOR_CONFIDENCE_HIGH,
    AUTHOR_CONFIDENCE_MEDIUM,
    AUTHOR_CONFIDENCE_NONE,
    AUTHOR_SOURCE_FOOTER_SIGNATURE,
    AUTHOR_SOURCE_HEADER,
    AUTHOR_SOURCE_NONE,
    AUTHOR_SOURCE_OPENING_PHRASE,
    body_contains_text,
    editorial_structure_to_dict,
    extract_editorial_structure,
    rebuild_editorial_text,
)


# =========================================================
# EMPTY
# =========================================================


def test_empty_text_is_safe():

    result = extract_editorial_structure(
        ""
    )

    assert result.title == ""
    assert result.author == ""
    assert result.body == ""
    assert (
        result.author_source
        == AUTHOR_SOURCE_NONE
    )
    assert (
        result.author_confidence
        == AUTHOR_CONFIDENCE_NONE
    )


# =========================================================
# TITLE
# =========================================================


def test_first_line_is_detected_as_title():

    text = (
        "پایان کشور دوست\n\n"
        "کشورها دیگر دوست ندارند. "
        "این گزاره توصیف جهان امروز است."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.title
        == "پایان کشور دوست"
    )

    assert (
        "کشورها دیگر دوست ندارند"
        in result.body
    )


def test_title_is_removed_from_body():

    text = (
        "پایان کشور دوست\n\n"
        "این نخستین پاراگراف متن است.\n\n"
        "این دومین پاراگراف متن است."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.title
        == "پایان کشور دوست"
    )

    assert (
        "پایان کشور دوست"
        not in result.body
    )


# =========================================================
# AUTHOR HEADER
# =========================================================


def test_author_in_header():

    text = (
        "پایان کشور دوست\n\n"
        "نویسنده: حامد محمدی\n\n"
        "کشورها دیگر دوست ندارند."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.title
        == "پایان کشور دوست"
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_HEADER
    )

    assert (
        result.author_confidence
        == AUTHOR_CONFIDENCE_HIGH
    )

    assert (
        "نویسنده"
        not in result.body
    )

    assert (
        "کشورها دیگر دوست ندارند"
        in result.body
    )


def test_author_with_be_ghalam_header():

    text = (
        "پایان کشور دوست\n\n"
        "به قلم حامد محمدی\n\n"
        "متن اصلی یادداشت از اینجا آغاز می‌شود."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_HEADER
    )


def test_author_with_yaddasht_az_header():

    text = (
        "پایان کشور دوست\n\n"
        "یادداشت از حامد محمدی\n\n"
        "متن اصلی یادداشت."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.author
        == "حامد محمدی"
    )


# =========================================================
# OPENING PHRASE
# =========================================================


def test_author_from_minevisad_phrase():

    text = (
        "پایان کشور دوست\n\n"
        "حامد محمدی می‌نویسد:\n\n"
        "کشورها دیگر دوست ندارند."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_OPENING_PHRASE
    )

    assert (
        result.author_confidence
        == AUTHOR_CONFIDENCE_HIGH
    )

    assert (
        "حامد محمدی می‌نویسد"
        not in result.body
    )

    assert (
        "کشورها دیگر دوست ندارند"
        in result.body
    )


def test_author_from_mi_nevisad_with_normal_space():

    text = (
        "پایان کشور دوست\n\n"
        "حامد محمدی می نویسد:\n\n"
        "جهان امروز شبکه است."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_OPENING_PHRASE
    )


def test_author_from_dar_yaddashti_minevisad():

    text = (
        "پایان کشور دوست\n\n"
        "حامد محمدی در یادداشتی می‌نویسد:\n\n"
        "جهان امروز شبکه است."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_OPENING_PHRASE
    )


def test_opening_phrase_remainder_is_preserved():

    text = (
        "پایان کشور دوست\n\n"
        "حامد محمدی می‌نویسد: کشورها دیگر دوست ندارند "
        "و روابط بر پایه منفعت موضوعی تعریف می‌شوند.\n\n"
        "پاراگراف دوم متن."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        "کشورها دیگر دوست ندارند"
        in result.body
    )

    assert (
        "روابط بر پایه منفعت موضوعی"
        in result.body
    )

    assert (
        "پاراگراف دوم متن"
        in result.body
    )

    assert (
        result.metadata[
            "opening_remainder_kept"
        ]
        is True
    )


# =========================================================
# FOOTER AUTHOR
# =========================================================


def test_author_in_footer():

    text = (
        "پایان کشور دوست\n\n"
        "این نخستین پاراگراف یادداشت است.\n\n"
        "این آخرین پاراگراف یادداشت است.\n\n"
        "حامد محمدی"
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_FOOTER_SIGNATURE
    )

    assert (
        result.author_confidence
        == AUTHOR_CONFIDENCE_MEDIUM
    )

    assert (
        "حامد محمدی"
        not in result.body
    )

    assert (
        "این نخستین پاراگراف"
        in result.body
    )

    assert (
        "این آخرین پاراگراف"
        in result.body
    )


def test_footer_author_with_title():

    text = (
        "پایان کشور دوست\n\n"
        "متن یادداشت.\n\n"
        "دکتر حامد محمدی"
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.author
        == "دکتر حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_FOOTER_SIGNATURE
    )


# =========================================================
# ONE-WORD FOOTER
# =========================================================


def test_one_word_footer_is_not_accepted_as_author():

    text = (
        "پایان کشور دوست\n\n"
        "این متن اصلی یادداشت است.\n\n"
        "حامد"
    )

    result = extract_editorial_structure(
        text
    )

    assert result.author == ""

    assert (
        result.author_source
        == AUTHOR_SOURCE_NONE
    )

    assert (
        "حامد"
        in result.body
    )


# =========================================================
# NO AUTHOR
# =========================================================


def test_text_without_author():

    text = (
        "پایان کشور دوست\n\n"
        "کشورها دیگر دوست ندارند.\n\n"
        "جهان امروز شبکه است."
    )

    result = extract_editorial_structure(
        text
    )

    assert result.author == ""

    assert (
        result.author_source
        == AUTHOR_SOURCE_NONE
    )

    assert (
        result.author_confidence
        == AUTHOR_CONFIDENCE_NONE
    )


# =========================================================
# BODY COVERAGE
# =========================================================


def test_body_preserves_first_middle_and_last_paragraphs():

    text = (
        "پایان کشور دوست\n\n"
        "پاراگراف اول درباره تغییر ماهیت روابط کشورهاست.\n\n"
        "پاراگراف دوم درباره جریان انرژی و تجارت است.\n\n"
        "پاراگراف سوم درباره دیپلماسی موضوعی است.\n\n"
        "پاراگراف چهارم درباره هزینه‌های این مدل است.\n\n"
        "پاراگراف پنجم درباره جایگاه ایران است.\n\n"
        "پاراگراف پایانی درباره جهان شبکه‌ای است."
    )

    result = extract_editorial_structure(
        text
    )

    assert body_contains_text(
        result,
        "پاراگراف اول درباره تغییر ماهیت روابط کشورهاست."
    )

    assert body_contains_text(
        result,
        "پاراگراف سوم درباره دیپلماسی موضوعی است."
    )

    assert body_contains_text(
        result,
        "پاراگراف پنجم درباره جایگاه ایران است."
    )

    assert body_contains_text(
        result,
        "پاراگراف پایانی درباره جهان شبکه‌ای است."
    )


def test_body_preserves_all_content_paragraphs():

    paragraphs = [
        "پاراگراف اول",
        "پاراگراف دوم",
        "پاراگراف سوم",
        "پاراگراف چهارم",
        "پاراگراف پنجم",
        "پاراگراف ششم",
    ]

    text = (
        "عنوان یادداشت\n\n"
        + "\n\n".join(
            paragraphs
        )
    )

    result = extract_editorial_structure(
        text
    )

    for paragraph in paragraphs:

        assert (
            paragraph
            in result.body
        )


# =========================================================
# TITLE + AUTHOR + BODY
# =========================================================


def test_complete_structure_header_author():

    text = (
        "پایان کشور دوست\n\n"
        "نویسنده: حامد محمدی\n\n"
        "پاراگراف اول یادداشت.\n\n"
        "پاراگراف دوم یادداشت.\n\n"
        "پاراگراف سوم یادداشت."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.title
        == "پایان کشور دوست"
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_HEADER
    )

    assert (
        "پاراگراف اول یادداشت."
        in result.body
    )

    assert (
        "پاراگراف دوم یادداشت."
        in result.body
    )

    assert (
        "پاراگراف سوم یادداشت."
        in result.body
    )


def test_complete_structure_opening_phrase():

    text = (
        "پایان کشور دوست\n\n"
        "حامد محمدی می‌نویسد: جهان امروز شبکه است.\n\n"
        "کشورها در هر موضوع رفتار متفاوتی دارند.\n\n"
        "همکاری در یک حوزه به معنای اتحاد کامل نیست."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.title
        == "پایان کشور دوست"
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        "جهان امروز شبکه است."
        in result.body
    )

    assert (
        "کشورها در هر موضوع رفتار متفاوتی دارند."
        in result.body
    )

    assert (
        "همکاری در یک حوزه به معنای اتحاد کامل نیست."
        in result.body
    )


# =========================================================
# REBUILD
# =========================================================


def test_rebuild_editorial_text_complete():

    rebuilt = rebuild_editorial_text(
        title="پایان کشور دوست",
        author="حامد محمدی",
        body="این خلاصه نهایی یادداشت است."
    )

    assert rebuilt == (
        "پایان کشور دوست\n\n"
        "حامد محمدی\n\n"
        "این خلاصه نهایی یادداشت است."
    )


def test_rebuild_without_author():

    rebuilt = rebuild_editorial_text(
        title="پایان کشور دوست",
        author="",
        body="این خلاصه نهایی یادداشت است."
    )

    assert rebuilt == (
        "پایان کشور دوست\n\n"
        "این خلاصه نهایی یادداشت است."
    )


def test_rebuild_without_title():

    rebuilt = rebuild_editorial_text(
        title="",
        author="حامد محمدی",
        body="متن خلاصه."
    )

    assert rebuilt == (
        "حامد محمدی\n\n"
        "متن خلاصه."
    )


# =========================================================
# DICT HELPER
# =========================================================


def test_structure_to_dict():

    text = (
        "پایان کشور دوست\n\n"
        "نویسنده: حامد محمدی\n\n"
        "متن اصلی."
    )

    structure = extract_editorial_structure(
        text
    )

    result = editorial_structure_to_dict(
        structure
    )

    assert (
        result[
            "title"
        ]
        == "پایان کشور دوست"
    )

    assert (
        result[
            "author"
        ]
        == "حامد محمدی"
    )

    assert (
        result[
            "author_source"
        ]
        == AUTHOR_SOURCE_HEADER
    )

    assert (
        result[
            "body"
        ]
        == "متن اصلی."
    )

    assert isinstance(
        result[
            "metadata"
        ],
        dict
    )


# =========================================================
# NO FALSE AUTHOR FROM NORMAL SENTENCE
# =========================================================


def test_normal_sentence_is_not_detected_as_author():

    text = (
        "پایان کشور دوست\n\n"
        "جهان امروز شبکه است و کشورها بر اساس "
        "منافع موضوعی تصمیم می‌گیرند.\n\n"
        "این روند بر سیاست خارجی اثر می‌گذارد."
    )

    result = extract_editorial_structure(
        text
    )

    assert result.author == ""

    assert (
        "جهان امروز شبکه است"
        in result.body
    )


# =========================================================
# FOOTER BRANDING MUST NOT BECOME AUTHOR
# =========================================================


def test_footer_hashtag_is_not_author():

    text = (
        "پایان کشور دوست\n\n"
        "متن اصلی یادداشت.\n\n"
        "#دنیا_۲۴_نیوز"
    )

    result = extract_editorial_structure(
        text
    )

    assert result.author == ""

    assert (
        "#دنیا_۲۴_نیوز"
        in result.body
    )


def test_footer_username_is_not_author():

    text = (
        "پایان کشور دوست\n\n"
        "متن اصلی یادداشت.\n\n"
        "@Donya24News"
    )

    result = extract_editorial_structure(
        text
    )

    assert result.author == ""

    assert (
        "@Donya24News"
        in result.body
    )


# =========================================================
# REALISTIC NOTE STRUCTURE
# =========================================================


def test_realistic_opinion_note_structure():

    text = (
        "پایان کشور دوست\n\n"
        "حامد محمدی می‌نویسد:\n\n"
        "کشورها دیگر دوست ندارند. این گزاره توصیف "
        "جهان امروز است و رابطه‌ها بیش از گذشته "
        "بر پایه منفعت موضوعی تعریف می‌شوند.\n\n"
        "این چندلایگی مفهوم کشور دوست را از کار "
        "انداخته و سیاست خارجی را مجبور کرده است "
        "از دسته‌بندی‌های ساده عبور کند.\n\n"
        "در چنین جهانی دیپلماسی باید توان تفکیک "
        "موضوع، زمان و منفعت داشته باشد.\n\n"
        "این رویکرد هزینه‌هایی نیز دارد و مدیریت "
        "هم‌زمان روابط پیچیده‌تر می‌شود.\n\n"
        "ایران نیز ناچار است روابط خود را بیش از "
        "گذشته بر پایه موضوع و منفعت تنظیم کند.\n\n"
        "در نهایت جهان امروز شبکه است نه بلوک و "
        "کشوری که نتواند این شبکه را مدیریت کند "
        "در حاشیه قرار خواهد گرفت."
    )

    result = extract_editorial_structure(
        text
    )

    assert (
        result.title
        == "پایان کشور دوست"
    )

    assert (
        result.author
        == "حامد محمدی"
    )

    assert (
        result.author_source
        == AUTHOR_SOURCE_OPENING_PHRASE
    )

    assert (
        "کشورها دیگر دوست ندارند"
        in result.body
    )

    assert (
        "دیپلماسی باید توان تفکیک"
        in result.body
    )

    assert (
        "ایران نیز ناچار است"
        in result.body
    )

    assert (
        "جهان امروز شبکه است نه بلوک"
        in result.body
    )
