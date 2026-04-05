from tools.export.markdown_converter import MarkdownConverter


def test_to_html_skips_template_sources_when_markdown_already_contains_sources_section():
    converter = MarkdownConverter()

    html = converter.to_html(
        "# AI chips\n\n## 来源\n\n- [1] [Annual Report](https://example.com/report)",
        title="AI chips",
        sources=["https://example.com/report"],
    )

    assert html.count("https://example.com/report") == 1
    assert "Sources</h2>" not in html
