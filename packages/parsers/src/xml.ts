export interface XmlNode {
  tag: string;
  attrs: Record<string, string>;
  children: XmlNode[];
  text: string;
}

const ENTITY_MAP: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
};

function decodeEntities(s: string): string {
  return s.replace(/&(#x?[0-9a-fA-F]+|\w+);/g, (m, body: string) => {
    if (body.startsWith("#x") || body.startsWith("#X")) {
      const code = Number.parseInt(body.slice(2), 16);
      return Number.isNaN(code) ? m : String.fromCodePoint(code);
    }
    if (body.startsWith("#")) {
      const code = Number.parseInt(body.slice(1), 10);
      return Number.isNaN(code) ? m : String.fromCodePoint(code);
    }
    return ENTITY_MAP[body] ?? m;
  });
}

export function parseXml(input: string): XmlNode {
  let i = 0;
  const root: XmlNode = { tag: "#root", attrs: {}, children: [], text: "" };
  const stack: XmlNode[] = [root];

  const skipWs = () => {
    while (i < input.length && /\s/.test(input[i]!)) i++;
  };

  const readTag = (): string => {
    const start = i;
    while (i < input.length && input[i] !== ">") i++;
    const raw = input.slice(start, i);
    i++;
    return raw;
  };

  const parseAttrs = (raw: string): { tag: string; attrs: Record<string, string> } => {
    const m = raw.match(/^([^\s/>]+)([\s\S]*)$/);
    if (!m) return { tag: raw.trim(), attrs: {} };
    const tag = m[1]!;
    const attrs: Record<string, string> = {};
    const attrRe = /([^\s=]+)\s*=\s*("([^"]*)"|'([^']*)')/g;
    let am: RegExpExecArray | null;
    while ((am = attrRe.exec(m[2] ?? ""))) {
      attrs[am[1]!] = decodeEntities(am[3] ?? am[4] ?? "");
    }
    return { tag, attrs };
  };

  while (i < input.length) {
    if (input[i] === "<") {
      if (input.startsWith("<!--", i)) {
        const end = input.indexOf("-->", i);
        i = end === -1 ? input.length : end + 3;
        continue;
      }
      if (input.startsWith("<![CDATA[", i)) {
        const end = input.indexOf("]]>", i);
        const cdata = input.slice(i + 9, end === -1 ? input.length : end);
        stack[stack.length - 1]!.text += cdata;
        i = end === -1 ? input.length : end + 3;
        continue;
      }
      if (input.startsWith("<?", i) || input.startsWith("<!", i)) {
        const end = input.indexOf(">", i);
        i = end === -1 ? input.length : end + 1;
        continue;
      }
      if (input[i + 1] === "/") {
        i += 2;
        const name = readTag().trim().replace(/\/$/, "");
        for (let s = stack.length - 1; s > 0; s--) {
          if (stack[s]!.tag === name) {
            stack.length = s;
            break;
          }
        }
        continue;
      }
      i++;
      const raw = readTag();
      const selfClosing = raw.endsWith("/");
      const { tag, attrs } = parseAttrs(selfClosing ? raw.slice(0, -1) : raw);
      const node: XmlNode = { tag, attrs, children: [], text: "" };
      stack[stack.length - 1]!.children.push(node);
      if (!selfClosing) stack.push(node);
      continue;
    }
    const start = i;
    while (i < input.length && input[i] !== "<") i++;
    const text = decodeEntities(input.slice(start, i));
    const top = stack[stack.length - 1]!;
    top.text += text;
  }

  return root;
}

export function findAll(node: XmlNode, tag: string, out: XmlNode[] = []): XmlNode[] {
  if (node.tag === tag) out.push(node);
  for (const c of node.children) findAll(c, tag, out);
  return out;
}

export function findAllWhere(
  node: XmlNode,
  pred: (n: XmlNode) => boolean,
  out: XmlNode[] = [],
): XmlNode[] {
  if (pred(node)) out.push(node);
  for (const c of node.children) findAllWhere(c, pred, out);
  return out;
}

export function childByTag(node: XmlNode, tag: string): XmlNode | undefined {
  return node.children.find((c) => c.tag === tag);
}

export function childrenByTag(node: XmlNode, tag: string): XmlNode[] {
  return node.children.filter((c) => c.tag === tag);
}

export function attrNum(n: XmlNode | undefined, name: string): number | undefined {
  if (!n) return undefined;
  const v = n.attrs[name];
  if (v === undefined) return undefined;
  const num = Number(v);
  return Number.isNaN(num) ? undefined : num;
}

export function attrStr(n: XmlNode | undefined, name: string): string | undefined {
  return n?.attrs[name];
}
