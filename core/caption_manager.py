def compact_long_text(
    text: str
) -> str:

    text = normalize_text(text)

    if not text:
        return ""

    content_lines: List[str] = []

    for line in text.splitlines():

        value = line.strip()

        if value:
            content_lines.append(value)

    if not content_lines:
        return ""

    title = content_lines[0]

    if len(content_lines) == 1:
        return title

    body_lines: List[str] = []

    for line in content_lines[1:]:

        value = line.strip()

        previous = None

        while (
            value
            and value != previous
        ):

            previous = value

            value = re.sub(
                (
                    r"^[\s\u200e\u200f"
                    r"\u202a-\u202e"
                    r"\u2066-\u2069]*"
                    r"🔹"
                    r"[\s\u200e\u200f"
                    r"\u202a-\u202e"
                    r"\u2066-\u2069]*"
                ),
                "",
                value,
                count=1
            ).lstrip()

        if value:
            body_lines.append(
                value
            )

    if not body_lines:
        return title

    result = (
        title
        + "\n\n"
        + "\n".join(
            body_lines
        )
    )

    logger.info(
        f"🗜️ Long text compacted | "
        f"before={len(text)} | "
        f"after={len(result)}"
    )

    return result
