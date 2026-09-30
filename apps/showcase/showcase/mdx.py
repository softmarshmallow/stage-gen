"""A deliberately small reader for the MDX the showcase pages are written in.

Supported, and valid MDX as written:
- TOML front matter between `+++` lines (remark-frontmatter reads the same block);
- `##` / `###` headings, paragraphs, `- ` bullet lists and fenced code blocks;
- inline `code`, **bold**, *emphasis* and [links](url);
- components, following MDX's own split: an element that sits alone on its lines is a block
  (`<Name prop="text" other={["json", 1]} />`), and one inside a sentence is inline
  (`make <Ref input="brief">this brief</Ref> into`). A block element whose opening tag ends its
  line holds blocks; one whose content follows on the same line holds a sentence.

Anything outside that subset is refused rather than guessed, so a page that builds here also
compiles under a real MDX toolchain later. Braces and stray `<` in prose are refused for that
reason.
"""

from __future__ import annotations

import html
import json
import re
import tomllib
from dataclasses import dataclass, field

TAG = re.compile(r"<([A-Z][A-Za-z0-9]*)")
ATTR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FENCE = re.compile(r"[ \t]*```([A-Za-z0-9_-]*)[ \t]*$")


class MdxError(ValueError):
    pass


@dataclass
class Heading:
    level: int
    text: str


@dataclass
class Paragraph:
    """A sentence: text runs and inline elements, in order."""

    parts: list


@dataclass
class ListBlock:
    items: list[str]


@dataclass
class CodeBlock:
    language: str
    code: str


@dataclass
class Element:
    name: str
    props: dict
    children: list | Paragraph | None = field(default=None)


def parse(source: str) -> tuple[dict, list]:
    front: dict = {}
    body = source
    if source.startswith("+++\n"):
        end = source.find("\n+++\n", 4)
        if end < 0:
            raise MdxError("front matter opened with +++ but never closed")
        front = tomllib.loads(source[4:end])
        body = source[end + 5 :]
    return front, blocks(body)


def _line_end(text: str, i: int) -> int:
    nl = text.find("\n", i)
    return len(text) if nl < 0 else nl


def _flow_element(text: str, i: int) -> tuple[Element, int] | None:
    """An element that starts at i and leaves nothing but whitespace on its last line."""
    if not TAG.match(text, i):
        return None
    element, end = _element(text, i)
    rest = text[end : _line_end(text, end)]
    return (element, end) if not rest.strip() else None


def blocks(text: str) -> list:
    out: list = []
    i = 0
    while i < len(text):
        while i < len(text) and text[i] in " \t\n":
            i += 1
        if i >= len(text):
            break
        if flow := _flow_element(text, i):
            out.append(flow[0])
            i = flow[1]
            continue
        line = text[i : _line_end(text, i)]
        if m := FENCE.match(line):
            close = re.compile(r"^[ \t]*```[ \t]*$", re.M).search(text, _line_end(text, i) + 1)
            if not close:
                raise MdxError("a ``` code block is never closed")
            code = text[_line_end(text, i) + 1 : close.start()]
            out.append(CodeBlock(m.group(1), code.rstrip("\n")))
            i = close.end()
            continue
        # A run of lines up to a blank line or a block element.
        lines: list[str] = []
        while i < len(text):
            end = _line_end(text, i)
            line = text[i:end]
            if not line.strip():
                break
            indent = len(line) - len(line.lstrip())
            if lines and (_flow_element(text, i + indent) or FENCE.match(line)):
                break
            lines.append(line.strip())
            i = end + 1
        chunk = "\n".join(lines)
        if m := re.match(r"(#{2,3})\s+(.*)", chunk):
            out.append(Heading(len(m.group(1)), _prose(m.group(2))))
        elif lines[0].startswith("- "):
            items: list[str] = []
            for line in lines:
                if line.startswith("- "):
                    items.append(line[2:])
                else:
                    items[-1] += " " + line
            out.append(ListBlock([_prose(item) for item in items]))
        else:
            out.append(Paragraph(_phrasing(" ".join(lines))))
    return out


def _prose(text: str) -> str:
    for bad in "{}<":
        if bad in text:
            raise MdxError(f"'{bad}' in prose is not valid MDX: {text[:80]!r}")
    return text


def _phrasing(text: str) -> list:
    """Split a sentence into text runs and inline elements."""
    parts: list = []
    pos = 0
    while (m := TAG.search(text, pos)) is not None:
        if m.start() > pos:
            parts.append(_prose(text[pos : m.start()]))
        element, pos = _element(text, m.start())
        parts.append(element)
    if pos < len(text):
        parts.append(_prose(text[pos:]))
    return parts


def _element(text: str, i: int) -> tuple[Element, int]:
    m = TAG.match(text, i)
    name, pos, props = m.group(1), m.end(), {}
    while True:
        while pos < len(text) and text[pos] in " \t\n":
            pos += 1
        if text.startswith("/>", pos):
            return Element(name, props), pos + 2
        if text.startswith(">", pos):
            pos += 1
            break
        a = ATTR.match(text, pos)
        if not a:
            raise MdxError(f"<{name}>: cannot read attribute at {text[pos : pos + 30]!r}")
        key, pos = a.group(0), a.end()
        if not text.startswith("=", pos):
            props[key] = True
            continue
        pos += 1
        if text.startswith('"', pos):
            close = text.index('"', pos + 1)
            props[key] = text[pos + 1 : close]
            pos = close + 1
        elif text.startswith("{", pos):
            close = _matching_brace(text, pos)
            try:
                props[key] = json.loads(text[pos + 1 : close])
            except json.JSONDecodeError as error:
                raise MdxError(f"<{name} {key}>: expression must be a JSON literal") from error
            pos = close + 1
        else:
            raise MdxError(f'<{name} {key}>: value must be "text" or {{json}}')
    closing = f"</{name}>"
    end = text.find(closing, pos)
    if end < 0:
        raise MdxError(f"<{name}> is never closed")
    inner = text[pos:end]
    if re.search(rf"<{name}[\s/>]", inner):
        raise MdxError(f"<{name}> may not contain another <{name}>")
    # MDX: content that starts on the opening tag's own line is a sentence; otherwise it is blocks.
    same_line = inner[: inner.find("\n")] if "\n" in inner else inner
    children: list | Paragraph = (
        blocks(inner) if not same_line.strip() else Paragraph(_phrasing(" ".join(inner.split())))
    )
    return Element(name, props, children), end + len(closing)


def _matching_brace(text: str, start: int) -> int:
    depth, i, quote = 0, start, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise MdxError("unbalanced { in an attribute")


def inline(text: str) -> str:
    """Escape, then render the inline Markdown the subset allows."""
    out = html.escape(text, quote=True)
    out = re.sub(r"`([^`]+)`", r'<code class="font-mono text-[0.9em]">\1</code>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", out)
    out = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        r'<a class="underline underline-offset-2" href="\2">\1</a>',
        out,
    )
    return out


def plain(text: str) -> str:
    """The same inline Markdown as plain text, for copying."""
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*|\*([^*]+)\*", lambda m: m.group(1) or m.group(2), text)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"\1 (\2)", text)
