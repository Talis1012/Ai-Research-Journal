import json

import streamlit.components.v1 as components


def render_markdown_toolbar(editor_key: str):
    selector = json.dumps(f".st-key-{editor_key} textarea")
    components.html(
        fr"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                * {{ box-sizing: border-box; }}
                html, body {{ margin: 0; padding: 0; background: transparent; }}
                .toolbar {{
                    height: 50px; display: flex; align-items: stretch;
                    overflow-x: auto; overflow-y: hidden;
                    border: 1px solid #cfdbea; border-radius: 9px 9px 0 0;
                    background: #ffffff; color: #172033;
                    font: 600 15px/1 Arial, sans-serif;
                }}
                .group {{ display: flex; align-items: stretch; border-right: 1px solid #e2e8f0; }}
                .group:last-child {{ border-right: 0; }}
                button, select {{
                    border: 0; background: transparent; color: #172033;
                    min-width: 40px; height: 48px; padding: 0 9px;
                    font: inherit; cursor: pointer; outline: none;
                }}
                button:hover, select:hover {{ background: #eef5ff; color: #0d65d9; }}
                button:focus-visible, select:focus-visible {{
                    box-shadow: inset 0 0 0 2px #1473e6;
                }}
                select {{ min-width: 116px; font-weight: 500; appearance: auto; }}
                .bold {{ font-size: 21px; font-weight: 850; }}
                .italic {{ font-family: Georgia, serif; font-size: 22px; font-style: italic; }}
                .list {{ font-size: 18px; letter-spacing: -1px; }}
                .indent {{ font-size: 20px; }}
                .link, .quote, .code {{ font-size: 19px; }}
                .quote {{ font-family: Georgia, serif; font-size: 25px; }}
                .sr-only {{
                    position: absolute; width: 1px; height: 1px; padding: 0;
                    margin: -1px; overflow: hidden; clip: rect(0,0,0,0);
                    white-space: nowrap; border: 0;
                }}
            </style>
        </head>
        <body>
            <div class="toolbar" role="toolbar" aria-label="Text formatting">
                <div class="group">
                    <label class="sr-only" for="block-style">Text style</label>
                    <select id="block-style" title="Text style" aria-label="Text style">
                        <option value="normal">Normal text</option>
                        <option value="h2">Heading 2</option>
                        <option value="h3">Heading 3</option>
                    </select>
                </div>
                <div class="group">
                    <button type="button" class="bold" data-command="bold" title="Bold (⌘/Ctrl+B)" aria-label="Bold">B</button>
                    <button type="button" class="italic" data-command="italic" title="Italic (⌘/Ctrl+I)" aria-label="Italic">I</button>
                </div>
                <div class="group">
                    <button type="button" class="list" data-command="bullet" title="Bulleted list" aria-label="Bulleted list">•☰</button>
                    <button type="button" class="list" data-command="number" title="Numbered list" aria-label="Numbered list">1☰</button>
                </div>
                <div class="group">
                    <button type="button" class="indent" data-command="indent" title="Increase indent" aria-label="Increase indent">≡›</button>
                    <button type="button" class="indent" data-command="outdent" title="Decrease indent" aria-label="Decrease indent">‹≡</button>
                </div>
                <div class="group">
                    <button type="button" class="link" data-command="link" title="Insert link" aria-label="Insert link">🔗</button>
                    <button type="button" class="quote" data-command="quote" title="Block quote" aria-label="Block quote">“</button>
                    <button type="button" class="code" data-command="code" title="Inline code" aria-label="Inline code">&lt;/&gt;</button>
                </div>
            </div>
            <script>
                const editorSelector = {selector};

                function editor() {{
                    return window.parent.document.querySelector(editorSelector);
                }}

                function replaceValue(target, value, selectionStart, selectionEnd) {{
                    const previousValue = target.value;
                    const prototype = window.parent.HTMLTextAreaElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(prototype, "value").set;
                    setter.call(target, value);

                    if (target._valueTracker) {{
                        target._valueTracker.setValue(previousValue);
                    }}

                    target.dispatchEvent(new window.parent.Event("input", {{ bubbles: true }}));
                    target.focus();
                    target.setSelectionRange(selectionStart, selectionEnd);
                    window.setTimeout(() => target.blur(), 0);
                }}

                function inlineWrap(before, after, placeholder) {{
                    const target = editor();
                    if (!target) return;
                    const start = target.selectionStart;
                    const end = target.selectionEnd;
                    const selected = target.value.slice(start, end) || placeholder;
                    const supportsMultipleLines = ["**", "_", "`"].includes(before);
                    const wrappedOutside = start >= before.length
                        && target.value.slice(start - before.length, start) === before
                        && target.value.slice(end, end + after.length) === after;

                    if (wrappedOutside) {{
                        const nextValue = target.value.slice(0, start - before.length)
                            + selected
                            + target.value.slice(end + after.length);
                        replaceValue(
                            target,
                            nextValue,
                            start - before.length,
                            end - before.length,
                        );
                        return;
                    }}

                    const replacement = supportsMultipleLines && selected.includes("\n")
                        ? selected.split("\n").map(line => {{
                            if (!line.trim()) return line;
                            const indentation = line.match(/^\s*/)[0];
                            const body = line.slice(indentation.length);
                            const alreadyWrapped = body.startsWith(before) && body.endsWith(after);
                            return alreadyWrapped
                                ? indentation + body.slice(before.length, -after.length)
                                : indentation + before + body + after;
                        }}).join("\n")
                        : selected.startsWith(before) && selected.endsWith(after)
                            ? selected.slice(before.length, -after.length)
                            : before + selected + after;
                    const multiline = supportsMultipleLines && selected.includes("\n");
                    const selectedWrapped = !multiline
                        && selected.startsWith(before)
                        && selected.endsWith(after);
                    const nextValue = target.value.slice(0, start) + replacement + target.value.slice(end);
                    const selectionStart = multiline || selectedWrapped
                        ? start
                        : start + before.length;
                    const selectionEnd = multiline || selectedWrapped
                        ? start + replacement.length
                        : selectionStart + selected.length;
                    replaceValue(target, nextValue, selectionStart, selectionEnd);
                }}

                function selectedLineRange(target) {{
                    const start = target.value.lastIndexOf("\n", Math.max(0, target.selectionStart - 1)) + 1;
                    const nextBreak = target.value.indexOf("\n", target.selectionEnd);
                    const end = nextBreak === -1 ? target.value.length : nextBreak;
                    return {{ start, end }};
                }}

                function transformLines(transform) {{
                    const target = editor();
                    if (!target) return;
                    const range = selectedLineRange(target);
                    const original = target.value.slice(range.start, range.end);
                    const lines = original.split("\n");
                    const replacement = transform(lines).join("\n");
                    const nextValue = target.value.slice(0, range.start) + replacement + target.value.slice(range.end);
                    replaceValue(target, nextValue, range.start, range.start + replacement.length);
                }}

                function cleanListPrefix(line) {{
                    return line.replace(/^(\s*)(?:[-*+]\s+|\d+\.\s+)/, "$1");
                }}

                function applyCommand(command) {{
                    if (command === "bold") inlineWrap("**", "**", "bold text");
                    if (command === "italic") inlineWrap("_", "_", "italic text");
                    if (command === "code") inlineWrap("`", "`", "code");
                    if (command === "link") inlineWrap("[", "](https://)", "link text");
                    if (command === "bullet") transformLines(lines => lines.map(line => line.trim() ? "- " + cleanListPrefix(line).trimStart() : line));
                    if (command === "number") transformLines(lines => {{
                        let number = 0;
                        return lines.map(line => line.trim()
                            ? (++number) + ". " + cleanListPrefix(line).trimStart()
                            : line);
                    }});
                    if (command === "indent") transformLines(lines => lines.map(line => line.trim() ? "    " + line : line));
                    if (command === "outdent") transformLines(lines => lines.map(line => line.replace(/^ {{1,4}}/, "")));
                    if (command === "quote") transformLines(lines => lines.map(line => line.trim() ? "> " + line.replace(/^>\s?/, "") : line));
                }}

                function applyBlockStyle(style) {{
                    transformLines(lines => lines.map(line => {{
                        const cleaned = line.replace(/^#{{1,6}}\s+/, "");
                        if (!cleaned.trim()) return cleaned;
                        if (style === "h2") return "## " + cleaned;
                        if (style === "h3") return "### " + cleaned;
                        return cleaned;
                    }}));
                }}

                document.querySelectorAll("button[data-command]").forEach(button => {{
                    button.addEventListener("mousedown", event => event.preventDefault());
                    button.addEventListener("click", () => applyCommand(button.dataset.command));
                }});

                document.getElementById("block-style").addEventListener("change", event => {{
                    applyBlockStyle(event.target.value);
                    event.target.value = "normal";
                }});

                function installShortcuts() {{
                    const target = editor();
                    if (!target || target.dataset.researchFormattingShortcuts) return;
                    target.dataset.researchFormattingShortcuts = "true";
                    target.addEventListener("keydown", event => {{
                        if (!(event.metaKey || event.ctrlKey)) return;
                        if (event.key.toLowerCase() === "b") {{
                            event.preventDefault();
                            inlineWrap("**", "**", "bold text");
                        }}
                        if (event.key.toLowerCase() === "i") {{
                            event.preventDefault();
                            inlineWrap("_", "_", "italic text");
                        }}
                    }});
                }}

                installShortcuts();
                window.setTimeout(installShortcuts, 150);
                window.setTimeout(installShortcuts, 600);
                window.setTimeout(installShortcuts, 1500);
            </script>
        </body>
        </html>
        """,
        height=50,
        scrolling=False,
    )
