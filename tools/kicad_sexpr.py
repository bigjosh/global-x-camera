"""Small lossless-enough S-expression reader/writer for KiCad project generation."""
import json
import re


class Atom(str):
    pass


def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack = []
    root = None
    for token in tokens:
        if token == '(':
            node = []
            if stack:
                stack[-1].append(node)
            else:
                root = node
            stack.append(node)
        elif token == ')':
            stack.pop()
        else:
            if token.startswith('"'):
                value = json.loads(token)
            else:
                value = Atom(token)
            stack[-1].append(value)
    assert not stack
    return root


def dumps(node):
    if isinstance(node, list):
        return '(' + ' '.join(dumps(x) for x in node) + ')'
    if isinstance(node, Atom):
        return str(node)
    if isinstance(node, str):
        return json.dumps(node, ensure_ascii=False)
    return str(node)


def children(node, key):
    return [n for n in node if isinstance(n, list) and n and n[0] == key]


def child(node, key, default=None):
    return next(iter(children(node, key)), default)
