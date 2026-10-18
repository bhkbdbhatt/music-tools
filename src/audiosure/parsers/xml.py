from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

ENTITY_MAP = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
}

_ENTITY_RE = re.compile(r"&(#[xX]?[0-9a-fA-F]+|\w+);")
_ATTR_RE = re.compile(r"([^\s=]+)\s*=\s*(\"([^\"]*)\"|'([^']*)')")
_TAG_HEAD_RE = re.compile(r"^([^\s/>]+)([\s\S]*)$")


@dataclass
class XmlNode:
    tag: str
    attrs: Dict[str, str] = field(default_factory=dict)
    children: List["XmlNode"] = field(default_factory=list)
    text: str = ""


def _decode_entities(s: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        body = m.group(1)
        if body.startswith("#x") or body.startswith("#X"):
            try:
                return chr(int(body[2:], 16))
            except ValueError:
                return m.group(0)
        if body.startswith("#"):
            try:
                return chr(int(body[1:]))
            except ValueError:
                return m.group(0)
        return ENTITY_MAP.get(body, m.group(0))

    return _ENTITY_RE.sub(repl, s)


def _parse_attrs(raw: str):
    m = _TAG_HEAD_RE.match(raw)
    if not m:
        return raw.strip(), {}
    tag = m.group(1)
    attrs = {}
    for am in _ATTR_RE.finditer(m.group(2) or ""):
        attrs[am.group(1)] = _decode_entities(am.group(3) if am.group(3) is not None else (am.group(4) or ""))
    return tag, attrs


def parse_xml(text: str) -> XmlNode:
    i = 0
    n = len(text)
    root = XmlNode(tag="#root")
    stack: List[XmlNode] = [root]

    def read_tag() -> str:
        nonlocal i
        start = i
        while i < n and text[i] != ">":
            i += 1
        raw = text[start:i]
        i += 1
        return raw

    while i < n:
        if text[i] == "<":
            if text.startswith("<!--", i):
                end = text.find("-->", i)
                i = n if end == -1 else end + 3
                continue
            if text.startswith("<![CDATA[", i):
                end = text.find("]]>", i)
                cdata = text[i + 9 : n if end == -1 else end]
                stack[-1].text += cdata
                i = n if end == -1 else end + 3
                continue
            if text.startswith("<?", i) or text.startswith("<!", i):
                end = text.find(">", i)
                i = n if end == -1 else end + 1
                continue
            if i + 1 < n and text[i + 1] == "/":
                i += 2
                name = read_tag().strip().rstrip("/")
                for s in range(len(stack) - 1, 0, -1):
                    if stack[s].tag == name:
                        del stack[s:]
                        break
                continue
            i += 1
            raw = read_tag()
            self_closing = raw.endswith("/")
            tag, attrs = _parse_attrs(raw[:-1] if self_closing else raw)
            node = XmlNode(tag=tag, attrs=attrs)
            stack[-1].children.append(node)
            if not self_closing:
                stack.append(node)
            continue
        start = i
        while i < n and text[i] != "<":
            i += 1
        stack[-1].text += _decode_entities(text[start:i])

    return root


def find_all(node: XmlNode, tag: str, out: Optional[List[XmlNode]] = None) -> List[XmlNode]:
    if out is None:
        out = []
    if node.tag == tag:
        out.append(node)
    for c in node.children:
        find_all(c, tag, out)
    return out


def find_all_where(
    node: XmlNode, pred: Callable[[XmlNode], bool], out: Optional[List[XmlNode]] = None
) -> List[XmlNode]:
    if out is None:
        out = []
    if pred(node):
        out.append(node)
    for c in node.children:
        find_all_where(c, pred, out)
    return out


def child_by_tag(node: XmlNode, tag: str) -> Optional[XmlNode]:
    for c in node.children:
        if c.tag == tag:
            return c
    return None


def children_by_tag(node: XmlNode, tag: str) -> List[XmlNode]:
    return [c for c in node.children if c.tag == tag]


def attr_num(n: Optional[XmlNode], name: str) -> Optional[float]:
    if not n:
        return None
    v = n.attrs.get(name)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def attr_str(n: Optional[XmlNode], name: str) -> Optional[str]:
    if not n:
        return None
    return n.attrs.get(name)
