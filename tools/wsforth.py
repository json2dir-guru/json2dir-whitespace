#!/usr/bin/env python3
"""wsforth: compiles a small Forth-like stack language into Whitespace assembly.

Usage: python3 tools/wsforth.py json2dir.wsf > json2dir.wsa
       python3 tools/wsasm.py json2dir.wsa > json2dir.ws

The output is readable assembly with one mnemonic per line (the same syntax that the
whitespacers interpreter accepts with `-f asm`); tools/wsasm.py turns it into the real,
invisible Whitespace program. Memory model (all on the Whitespace heap):
  * heap[0] is the frame pointer FP, heap[1] a scratch cell for input, globals follow;
  * every function call pushes a frame of its arguments + locals at FP (so recursion works);
    FP points just past the current frame;
  * array k lives at heap[(k+1) * 2^24 + i];
  * calls and returns use Whitespace's own call stack (call / ret).

Source language (whitespace separated words, `\\ comment` to end of line):
  var NAME                      global cell, starts at 0
  array NAME                    NAME@ ( i -- v )  NAME! ( v i -- )
  : NAME { a b | c d } ... ;    function; a b are popped from the stack, c d are locals
  NAME@ NAME!                   fetch / store a local or global
  123 -4 'c                     literals
  + - * / % dup drop swap not = <> < > <= >= and or emit halt
  getn                          read a decimal number line from stdin ( -- n )
  getb                          read one raw byte from stdin ( -- b )
  if ... else ... then   begin ... while ... repeat   begin ... until
  return                        leave the current function
  ." text"                      print text (\\n is a newline, \\\\ a backslash, \\" a quote)
  fail" text"                   print "json2dir: text" and a newline, then halt
Any other word calls the function of that name. Execution starts at `main`.
"""
import re
import sys

FP, SCRATCH, GLOBAL0, FRAME0, ARRAY_STRIDE = 0, 1, 2, 1000, 1 << 24


def tokenize(text):
    toks, i, n = [], 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        j = i
        while j < n and not text[j].isspace():
            j += 1
        w = text[i:j]
        if w == '\\':
            while j < n and text[j] != '\n':
                j += 1
            i = j
            continue
        if w in ('."', 'fail"'):
            k, out = j + 1, []
            while text[k] != '"':
                if text[k] == '\\' and text[k + 1] in 'n"\\':
                    out.append({'n': '\n'}.get(text[k + 1], text[k + 1]))
                    k += 2
                else:
                    out.append(text[k])
                    k += 1
            toks.append((w, ''.join(out)))
            i = k + 1
            continue
        toks.append((w, None))
        i = j
    return toks


class Compiler:
    def __init__(self):
        self.globals = {}
        self.arrays = {}
        self.funcs = set()
        self.out = []
        self.nlab = 0

    def label(self, hint):
        self.nlab += 1
        return '%s_%d' % (hint, self.nlab)

    def ins(self, *lines):
        for line in lines:
            self.out.append('    ' + line)

    def mark(self, lab):
        self.out.append(lab + ':')

    def bool_from(self, jump):
        """Turns the top of the stack into 1 if `jump` (jz/jn) would be taken, else 0."""
        t, e = self.label('t'), self.label('e')
        self.ins('%s %s' % (jump, t), 'push 0', 'jmp ' + e)
        self.mark(t)
        self.ins('push 1')
        self.mark(e)

    def prim(self, w):
        if w in ('+', '-', '*', '/', '%'):
            self.ins({'+': 'add', '-': 'sub', '*': 'mul', '/': 'div', '%': 'mod'}[w])
        elif w == 'dup':
            self.ins('dup')
        elif w == 'drop':
            self.ins('pop')
        elif w == 'swap':
            self.ins('swap')
        elif w == 'not':
            self.bool_from('jz')
        elif w == '=':
            self.ins('sub')
            self.bool_from('jz')
        elif w == '<>':
            self.ins('sub')
            self.bool_from('jz')
            self.bool_from('jz')
        elif w == '<':
            self.ins('sub')
            self.bool_from('jn')
        elif w == '>':
            self.ins('swap', 'sub')
            self.bool_from('jn')
        elif w == '<=':
            self.ins('swap', 'sub')
            self.bool_from('jn')
            self.bool_from('jz')
        elif w == '>=':
            self.ins('sub')
            self.bool_from('jn')
            self.bool_from('jz')
        elif w == 'and':
            self.ins('mul')
            self.bool_from('jz')
            self.bool_from('jz')
        elif w == 'or':
            # a or b = not (not a * not b)
            self.bool_from('jz')
            self.ins('swap')
            self.bool_from('jz')
            self.ins('mul')
            self.bool_from('jz')
        elif w == 'emit':
            self.ins('pchr')
        elif w == 'halt':
            self.ins('exit')
        elif w == 'getn':
            self.ins('push %d' % SCRATCH, 'inum', 'push %d' % SCRATCH, 'get')
        elif w == 'getb':
            self.ins('push %d' % SCRATCH, 'ichr', 'push %d' % SCRATCH, 'get')
        else:
            return False
        return True

    def text(self, s):
        for ch in s.encode('utf-8'):
            self.ins('push %d' % ch, 'pchr')

    def compile(self, text):
        toks = tokenize(text)
        i = 0
        while i < len(toks):
            w = toks[i][0]
            if w == 'var':
                self.globals[toks[i + 1][0]] = GLOBAL0 + len(self.globals)
                i += 2
            elif w == 'array':
                self.arrays[toks[i + 1][0]] = (len(self.arrays) + 1) * ARRAY_STRIDE
                i += 2
            elif w == ':':
                self.funcs.add(toks[i + 1][0])
                i += 2
            else:
                i += 1
        self.out.append('; generated by tools/wsforth.py - do not edit')
        self.mark('start')
        self.ins('push %d' % FP, 'push %d' % FRAME0, 'set')
        for k in self.globals.values():
            self.ins('push %d' % k, 'push 0', 'set')
        self.ins('call f_main', 'exit')
        i = 0
        while i < len(toks):
            w = toks[i][0]
            if w in ('var', 'array'):
                i += 2
            elif w == ':':
                i = self.function(toks, i + 1)
            else:
                raise SystemExit('unexpected word at top level: ' + w)
        return '\n'.join(self.out) + '\n'

    def laddr(self, k):
        k -= self.fs
        self.ins('push %d' % FP, 'get')
        if k:
            self.ins('push %d' % k, 'add')

    def function(self, toks, i):
        name = toks[i][0]
        i += 1
        args, locs = [], []
        if toks[i][0] == '{':
            i += 1
            target = args
            while toks[i][0] != '}':
                if toks[i][0] == '|':
                    target = locs
                else:
                    target.append(toks[i][0])
                i += 1
            i += 1
        local = {v: k for k, v in enumerate(args + locs)}
        fs = self.fs = len(local)
        exit_lab = 'x_' + name
        self.out.append('')
        self.out.append('; : %s { %s | %s }' % (name, ' '.join(args), ' '.join(locs)))
        self.mark('f_' + name)
        if fs:
            self.ins('push %d' % FP, 'push %d' % FP, 'get', 'push %d' % fs, 'add', 'set')
        for a in reversed(args):
            self.laddr(local[a])
            self.ins('swap', 'set')
        ctrl = []
        while True:
            w, s = toks[i]
            i += 1
            if w == ';':
                break
            if re.fullmatch(r'-?\d+', w):
                self.ins('push %d' % int(w))
            elif len(w) == 2 and w[0] == "'":
                self.ins('push %d' % ord(w[1]))
            elif w == '."':
                self.text(s)
            elif w == 'fail"':
                self.text('json2dir: ' + s + '\n')
                self.ins('exit')
            elif self.prim(w):
                pass
            elif w == 'if':
                lf = self.label('else')
                self.ins('jz ' + lf)
                ctrl.append(['if', lf])
            elif w == 'else':
                c = ctrl[-1]
                assert c[0] == 'if'
                lend = self.label('endif')
                self.ins('jmp ' + lend)
                self.mark(c[1])
                ctrl[-1] = ['else', lend]
            elif w == 'then':
                c = ctrl.pop()
                assert c[0] in ('if', 'else')
                self.mark(c[1])
            elif w == 'begin':
                lb = self.label('begin')
                self.mark(lb)
                ctrl.append(['begin', lb])
            elif w == 'while':
                c = ctrl[-1]
                assert c[0] == 'begin'
                lexit = self.label('wend')
                self.ins('jz ' + lexit)
                ctrl[-1] = ['while', c[1], lexit]
            elif w == 'repeat':
                c = ctrl.pop()
                assert c[0] == 'while'
                self.ins('jmp ' + c[1])
                self.mark(c[2])
            elif w == 'until':
                c = ctrl.pop()
                assert c[0] == 'begin'
                self.ins('jz ' + c[1])
            elif w == 'return':
                self.ins('jmp ' + exit_lab)
            elif w.endswith('@') or w.endswith('!'):
                v, op = w[:-1], w[-1]
                if v in local:
                    self.laddr(local[v])
                elif v in self.globals:
                    self.ins('push %d' % self.globals[v])
                elif v in self.arrays:
                    self.ins('push %d' % self.arrays[v], 'add')
                else:
                    raise SystemExit('unknown variable in %s: %s' % (name, w))
                if op == '@':
                    self.ins('get')
                else:
                    self.ins('swap', 'set')
            elif w in self.funcs:
                self.ins('call f_' + w)
            else:
                raise SystemExit('unknown word in %s: %s' % (name, w))
        assert not ctrl, 'unbalanced control words in ' + name
        self.mark(exit_lab)
        if fs:
            self.ins('push %d' % FP, 'push %d' % FP, 'get', 'push %d' % fs, 'sub', 'set')
        self.ins('ret')
        return i


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: wsforth.py SOURCE.wsf > OUT.wsa')
    with open(sys.argv[1], encoding='utf-8') as f:
        text = f.read()
    sys.stdout.buffer.write(Compiler().compile(text).encode('ascii'))


if __name__ == '__main__':
    main()
