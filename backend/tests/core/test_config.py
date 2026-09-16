from app.core.config import Settings


def test_cors_allowed_origins_parses_comma_separated_list():
    settings = Settings(
        CORS_ALLOWED_ORIGINS="https://a.example.com, https://b.example.com"
    )

    assert settings.cors_allowed_origins == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_cors_allowed_origins_empty_by_default():
    settings = Settings(CORS_ALLOWED_ORIGINS="")

    assert settings.cors_allowed_origins == []
