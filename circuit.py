import json
from collections import defaultdict

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

def load_circuit():
    nodenames = json.load(open('nodenames.json','r'))
    segdefs = json.load(open('segdefs.json','r'))
    transdefs = json.load(open('transdefs.json','r'))

    map_nodeattrib = {}
    segdefs_out = defaultdict(list)

    for t in segdefs:
        node = t[0]
        pullup = t[1] == '+'
        segdefs_out[node].append(t[2:])
        map_nodeattrib[node] = [0,NODE_PULLUP][pullup]

    n_nodes = max(map_nodeattrib.keys()) + 1

    print('Number of nodes %i'% n_nodes)
    print('Number of nodes with attributes %i'% len(map_nodeattrib))
    print('Number of nodes with names %i'% len(nodenames))

    nodedefs = [[NODE_UNDEFINED, None] for _ in range(n_nodes)]

    for k,v in map_nodeattrib.items():
        nodedefs[k][0] = v
    for k,v in nodenames.items():
        nodedefs[v][1] = k

    nodedefs[nodenames['vss']][0] |= NODE_GND
    nodedefs[nodenames['vcc']][0] |= NODE_PWR

    return Circuit(nodedefs, transdefs, dict(segdefs_out), nodenames['vss'], nodenames['vcc'])
