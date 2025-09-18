from patch_gui.ai_conflict_helper import build_conflict_suggestion


def test_build_conflict_suggestion_provides_patch_and_reason() -> None:
    file_context = ["alpha\n", "beta\n", "gamma\n"]
    suggestion = build_conflict_suggestion(
        file_context,
        failure_reason="unable to locate target block",
        before_lines=["beta\n"],
        after_lines=["BETA\n"],
        header="@@ -2 +2 @@",
    )
    text = suggestion.as_text()
    assert "Motivo del fallimento: unable to locate target block" in text
    assert "Patch suggerita:" in text
    assert "+BETA" in text
    assert "beta" in text
