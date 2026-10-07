#!/usr/bin/env python3
"""wsasm: assembles readable Whitespace assembly into a Whitespace program.

Usage: python3 tools/wsasm.py json2dir.wsa > json2dir.ws

One instruction per line, `;` starts a comment, `NAME:` defines a label.
  Stack:   push N   dup   copy N   swap   pop   slide N
  Arith:   add   sub   mul   div   mod
  Heap:    set (store: addr value --)   get (retrieve: addr -- value)
  Flow:    label L / L:   call L   jmp L   jz L   jn L   ret   exit
  I/O:     pchr   pnum   ichr   inum
The output consists only of space, tab and linefeed. Labels are numbered in order of
first appearance and written as the binary digits of that number (space 0, tab 1).
"""
import sys

S, T, L = ' ', '\t', '\n'

SIMPLE = {
    'dup': S + L + S, 'swap': S + L + T, 'pop': S + L + L,
    'add': T + S + S + S, 'sub': T + S + S + T, 'mul': T + S + S + L,
    'div': T + S + T + S, 'mod': T + S + T + T,
    'set': T + T + S, 'get': T + T + T,
    'ret': L + T + L, 'exit': L + L + L,
    'pchr': T + L + S + S, 'pnum': T + L + S + T,
    'ichr': T + L + T + S, 'inum': T + L + T + T,
}
WITH_NUMBER = {'push': S + S, 'copy': S + T + S, 'slide': S + T + L}
WITH_LABEL = {'label': L + S + S, 'call': L + S + T, 'jmp': L + S + L,
              'jz': L + T + S, 'jn': L + T + T}


def number(n):
    sign = S if n >= 0 else T
    bits = bin(abs(n))[2:] if n else ''
    return sign + bits.replace('0', S).replace('1', T) + L


def assemble(text):
    labels = {}

    def lab(name):
        if name not in labels:
            labels[name] = len(labels) + 1
        return bin(labels[name])[2:].replace('0', S).replace('1', T) + L

    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.split(';', 1)[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            line = 'label ' + line[:-1]
        parts = line.split()
        op, args = parts[0], parts[1:]
        if op in SIMPLE and not args:
            out.append(SIMPLE[op])
        elif op in WITH_NUMBER and len(args) == 1:
            out.append(WITH_NUMBER[op] + number(int(args[0])))
        elif op in WITH_LABEL and len(args) == 1:
            out.append(WITH_LABEL[op] + lab(args[0]))
        else:
            raise SystemExit('line %d: cannot assemble %r' % (lineno, line))
    return ''.join(out)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: wsasm.py SOURCE.wsa > OUT.ws')
    with open(sys.argv[1], encoding='ascii') as f:
        text = f.read()
    sys.stdout.buffer.write(assemble(text).encode('ascii'))


if __name__ == '__main__':
    main()
