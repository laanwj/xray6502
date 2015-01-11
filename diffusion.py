# Diffusion test
from __future__ import division, print_function

NODE_PULLUP = 1
NODE_PULLDOWN = 2
NODE_GND = 4
NODE_PWR = 8
NODE_UNDEFINED = 16

TRANS_DUPLICATE = 1

class Node:
    def __init__(self, i, d):
        self.id = i
        self.flags = d[0]
        self.name = d[1]
        self.gates = []
        self.c1s = []
        self.c2s = []
        self.sibs = []

    def __str__(self):
        flags = ''
        if self.flags & NODE_PULLUP:
            flags = '+'
        if self.flags & NODE_PULLDOWN:
            flags = '-'
        if self.name is not None:
            return 'N%i%s (%s)' % (self.id, flags, self.name)
        else:
            return 'N%i%s' % (self.id, flags)

class Transistor:
    def __init__(self, i, t):
        self.id = i
        self.name = t[0]
        self.gate = t[1] # gate
        self.c1 = t[2] # source
        self.c2 = t[3] # drain
        self.flags = 0

    def __str__(self):
        return self.name

class Circuit:
    def __init__(self, nodedefs, transdefs, segdefs, gnd, pwr):
        self.node = [Node(i,d) for i,d in enumerate(nodedefs)]
        self.trans = [Transistor(i,t) for i,t in enumerate(transdefs)]
        self.seg = segdefs
        self.gnd = gnd
        self.pwr = pwr
        # eliminate duplicate or shorting transistors
        dupes = set()
        for t in self.trans:
            spec = (t.gate, t.c1, t.c2)
            spec2 = (t.gate, t.c2, t.c1)
            if spec in dupes or spec2 in dupes or t.c1==t.c2:
                t.flags |= TRANS_DUPLICATE
            else:
                dupes.add(spec)
        # cross-reference non-duplicate transisitors
        for t in self.trans:
            if t.flags & TRANS_DUPLICATE:
                continue
            self.node[t.gate].gates.append(t.id)
            self.node[t.c1].c1s.append(t.id)
            self.node[t.c2].c2s.append(t.id)

            self.node[t.c1].sibs.append((t.gate, t.c2))
            self.node[t.c2].sibs.append((t.gate, t.c1))

def colorize(str, col):
    return ('\x1b[38;5;%im' % col) + str + ('\x1b[0m')

STATE_LO = 0x00
STATE_HI = 0x01
STATE_PULLUP = 0x03
STATE_PULLDOWN = 0x04
STATE_PWR = 0x05
STATE_GND = 0x06
STATE_RESET_HI = 0x07
STATE_RESET_LO = 0x08

v_states = {
STATE_LO:colorize('-', 52),
STATE_HI:colorize('+', 22),
STATE_PULLUP:colorize('+', 88),
STATE_PULLDOWN:colorize('-', 124),
STATE_PWR:colorize('+', 77),
STATE_GND:colorize('-', 167),
STATE_RESET_HI:colorize('X', 77),
STATE_RESET_LO:colorize('X', 167),
}

def diffuse(c):
    while True:
        print(''.join(v_states[n.state] for n in c.node))
        changed = 0
        for t in c.trans:
            # spread reset first
            if c.node[t.gate].state == STATE_RESET_LO or c.node[t.gate].state == STATE_RESET_HI:
                c.node[t.c1].state = [STATE_RESET_LO,STATE_RESET_HI][c.node[t.c1].state&1]
                c.node[t.c2].state = [STATE_RESET_LO,STATE_RESET_HI][c.node[t.c1].state&1]
                changed += 1
                reset(c.node[t.gate])

            if c.node[t.gate].state & 1:
                state = max(c.node[t.c1].state, c.node[t.c2].state)
                if c.node[t.c1].state != state:
                    changed += 1
                    c.node[t.c1].state = state
                if c.node[t.c2].state != state:
                    changed += 1
                    c.node[t.c2].state = state

        if not changed:
            break

def reset(node):
    node.state = STATE_LO
    if node.flags & NODE_PULLUP:
       node.state = max(node.state, STATE_PULLUP)
    if node.flags & NODE_PULLDOWN:
       node.state = max(node.state, STATE_PULLDOWN)
    if node.flags & NODE_GND:
       node.state = max(node.state, STATE_GND)
    if node.flags & NODE_PWR:
       node.state = max(node.state, STATE_PWR)

def main():
    node_gnd = 0
    node_pwr = 1
    node_t = 2
    node_i0 = 3
    node_i1 = 4
    nodedefs = [
        [NODE_GND, 'gnd'],
        [NODE_PWR, 'pwr'],
        [NODE_PULLUP, 't'],
        [NODE_PULLUP, 'i0'],
        [NODE_PULLUP, 'i1'],
    ]
    transdefs = [
        [None, node_i0, node_t, node_gnd],
        [None, node_i1, node_t, node_gnd],
    ]
    c = Circuit(nodedefs, transdefs, None, node_gnd, node_pwr)

    for node in c.node:
        node.reset = 0
        node.state = 0

    c.node[node_i0].flags = NODE_PULLDOWN
    c.node[node_i0].state = STATE_RESET_HI
    c.node[node_i1].flags = NODE_PULLDOWN
    c.node[node_i1].state = STATE_RESET_HI
    #reset(c.node[node_i0])
    #reset(c.node[node_i1])

    diffuse(c)
    print('result: t %s' % (v_states[c.node[node_t].state]))

main()

