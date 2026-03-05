from api.services.chat.language import (
    build_response_language_rule,
    infer_user_language_code,
    resolve_response_language,
)


def test_resolve_response_language_prefers_explicit_request() -> None:
    resolved = resolve_response_language("fr-FR", "What is this PDF about?")
    assert resolved == "fr"


def test_infer_user_language_code_detects_spanish() -> None:
    resolved = infer_user_language_code("Que hace esta empresa y como funciona su modelo de negocio?")
    assert resolved == "es"


def test_infer_user_language_code_detects_arabic_script() -> None:
    resolved = infer_user_language_code("ما الذي تفعله هذه الشركة؟")
    assert resolved == "ar"


def test_build_response_language_rule_uses_detected_language_label() -> None:
    rule = build_response_language_rule(
        requested_language=None,
        latest_message="Que hace esta empresa y como funciona su modelo de negocio?",
    )
    assert "Spanish" in rule

