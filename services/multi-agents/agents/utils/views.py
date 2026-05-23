import mistune

_DOC_CSS = """
<style>
body { font-family: 'Segoe UI', system-ui, sans-serif; line-height: 1.7; color: #222; max-width: 860px; margin: 0 auto; padding: 2rem; }
h1 { font-size: 2rem; border-bottom: 2px solid #e5e7eb; padding-bottom: .5rem; margin-bottom: 1.5rem; }
h2 { font-size: 1.5rem; margin-top: 2rem; color: #1d4ed8; }
h3 { font-size: 1.2rem; margin-top: 1.5rem; }
p { margin: .75rem 0; }
code { background: #f3f4f6; padding: .15em .4em; border-radius: 4px; font-size: .9em; }
pre { background: #1e293b; color: #e2e8f0; padding: 1.2rem; border-radius: 8px; overflow-x: auto; }
pre code { background: none; padding: 0; color: inherit; }
blockquote { border-left: 4px solid #3b82f6; padding-left: 1rem; color: #555; margin: 1rem 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #d1d5db; padding: .6rem .9rem; text-align: left; }
th { background: #f9fafb; font-weight: 600; }
ul, ol { padding-left: 1.5rem; margin: .75rem 0; }
li { margin: .3rem 0; }
a { color: #2563eb; }
</style>
"""


def markdown_to_html(md: str, standalone: bool = False) -> str:
    """Convert Markdown string to HTML fragment or full document."""
    renderer = mistune.HTMLRenderer(escape=False)
    md_parser = mistune.create_markdown(renderer=renderer, plugins=["table", "strikethrough", "footnotes"])
    body = md_parser(md)
    if standalone:
        return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{_DOC_CSS}</head><body>{body}</body></html>"
    return f"{_DOC_CSS}<div class='doc-gen-content'>{body}</div>"
