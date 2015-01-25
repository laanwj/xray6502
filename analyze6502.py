# coding: utf-8
'''
Convert 6502 data from json files to our own
data format.
'''
from __future__ import division, print_function
import json
import sys
from collections import defaultdict

# simple 'incremental state machine' sim:
#   four state logic (0=lo, 1=hi, 2=float_lo, 3=float_hi): min(A,B)
#
# w/ AND
#   000 lo
#   001 hi
#   011 float_lo
#   111 float_hi
#
#   need to propagate float_lo/float_hi but only when lo/hi is not asserted
#   (e.g. when no lo or hi is coming in via any path)
#   are transistors oriented? does it matter which side (c1,c2) is high and low? NO
#   if connected to group that has lo/hi (we know where these can flow in)
#
#   *if in any of the active group*:
#     pull-up causes hi 
#     PWR causes hi
#     pull-down causes lo
#     GND causes lo
#     otherwise: float state
#
#   A&B
#   pull-up and pull-down nodes can only be lo or hi, not float
#
#   also need a 'changed' bit, to detect when to recompute?
#
#   for every transistor, if enabled: diffuse
#
#      active[c1] = active[c2] = min(active[c1],active[c2],boundary[c1],boundary[c2])
#
#   boundary conditions (e.g, vcc, gnd, pullup, pulldown cannot change, will always return same, and
#     bound the state value at the top)
#
#   if transistor gate value changes, add it to work list
#   if transistor c1 value changes, add it to work list
#   if transistor c2 value changes, add it to work list
#
#  'transistor switching off' is the difficult case because it can create two isolated islands
#  entire group needs recomputation
#    set 'reset bit' for node c1 and c2 of transistor
#    this bit propagates over diffusion boundaries every step, and resets the state to 'float hi' or 'float lo',
#      then clears the reset bit again
#
#  Diffusion algorithm:
#      if nodeState[c1] & RESET:
#          nodeState[c2] |= RESET
#          nodeState]c1] &= RESET
#          nodeState]c1] &= ASSERTED
#      else if nodeState[c2] & RESET:
#          nodeState[c1] |= RESET
#          nodeState]c2] &= RESET
#          nodeState]c1] &= ASSERTED
#      if (nodeState[c1] & ASSERTED) and (nodeState[c2] & ASSERTED):
#          nodeState[c1] = 
#
# Per-group simulation ('bounding groups')
#   - sort nodes per group
#   - have bitfields per group
#     - e.g., nodes_pullup, nodes_pulldown, nodes_value
#     - VSS and VCC could be replicated per group
#   - group inputs: gates that control subdivision
#   - group outputs: inputs (other transistor gates) controlled by this group

#   - nodeGroup(n, nodesActive, siblings) = [n] ∪ [nodeGroup(x) if nodesActive[y] for x,y in siblings[n]]
#
#         siblings is constant throughout the simulation
#         nodesActive is variable - only node values inside siblings[n] for the bounding group are queried
#
#     nodeGroup(gnd) = [gnd]
#
#     nodeGroup(pwr) = [pwr]
#
#     nodeValue(n, nodesPullDown, nodesPullUp, nodesActive) = 
#         | contains_vss if n = vss
#         | contains_vcc if n = vcc
#         | contains_pulldown if n in nodesPullDown
#         | contains_pullup if n in nodesPullUp
#         | contains_hi if n in nodesActive
#         | contains_nothing
#
#     groupContains(g, nodesPullDown, nodesPullUp, nodesActive) = min x: nodeValue(x, nodesPullDown, nodesPullUp, nodesActive) for x in in g
#
#     groupValue(x) = 
#         | 0 if x = contains_vss
#         | 1 if x = contains_vcc
#         | 0 if x = contains_pulldown
#         | 1 if x = contains_pullup
#         | 0 if x = contains_nothing
#         | 1 if x = contains_hi
#
#  Update:
#
#     nodesActive[g] = groupValue(groupContains(g, nodesPullDown, nodesPullUp, nodesActive))

NODE_PULLUP = 1
NODE_PULLDOWN = 2
NODE_GND = 4
NODE_PWR = 8
NODE_UNDEFINED = 16

TRANS_DUPLICATE = 1

layer_names = ['metal', 'switched diffusion', 'inputdiode', 'grounded diffusion', 'powered diffusion', 'polysilicon']

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

class CircuitTree:
    def __init__(self, o, c, max_depth=5):
        self.c = c
        self.o = o
        self.max_depth = max_depth
        self.v_node = set()
        self.v_trans = set()

    def dump_transistor(self, t, indent=0):
        s = '  '*indent
        trans = self.c.trans[t]
        if t in self.v_trans or indent>self.max_depth:
            return
        self.v_trans.add(t)
        self.o.write('%s%s\n' % (s, trans.name))
        self.o.write('%sGate: ' % (s))
        self.dump_node(trans.gate, indent+1)
        self.o.write('%sC1: ' % (s))
        self.dump_node(trans.c1, indent+1)
        self.o.write('%sC2: ' % (s))
        self.dump_node(trans.c2, indent+1)

    def dump_node(self, n, indent=0):
        s = '  '*indent
        node = self.c.node[n]
        if n in self.v_node or node.flags & (NODE_GND | NODE_PWR) or indent>self.max_depth:
            self.o.write('%s\n' % (str(node)))
            return
        self.v_node.add(n)
        self.o.write('%s\n' % (str(node)))
        self.o.write('%sGates:\n' % (s))
        for t in node.gates:
            self.dump_transistor(t, indent+1)
        self.o.write('%sC1C2:\n' % (s))
        for t in node.c1s + node.c2s:
            self.dump_transistor(t, indent+1)

def find_connected_components(c, obj, bits=7):
    worklist = [obj]
    v_node = set()
    v_trans = set()
    while worklist:
        item = worklist.pop()
        if isinstance(item, Transistor):
            if item.id in v_trans:
                continue
            v_trans.add(item.id)
            if bits & 1:
                worklist.append(c.node[item.gate])
            if bits & 2:
                worklist.append(c.node[item.c1])
            if bits & 4:
                worklist.append(c.node[item.c2])
        elif isinstance(item, Node):
            assert(not (item.flags & NODE_UNDEFINED))
            if item.id in v_node or item.flags & (NODE_GND|NODE_PWR):
                continue
            v_node.add(item.id)
            if bits & 1:
                worklist.extend([c.trans[t] for t in item.gates])
            if bits & 6:
                worklist.extend([c.trans[t] for t in item.c1s])
                worklist.extend([c.trans[t] for t in item.c2s])
        else:
            raise ValueError
    return (v_node, v_trans)

def main():
    c = load_circuit()
    '''
    CircuitTree(sys.stdout,c,10).dump_node(103)
    '''
    '''
    for i,node in enumerate(c.node):
        if node.name is None:
            name = ''
        else:
            name = node.name
        print('%4i %i %s' % (i,node.flags,name))
    '''
    '''
    for t in c.trans:
        gate = c.node[t.gate]
        c1 = c.node[t.c1]
        c2 = c.node[t.c2]
        if gate.flags & NODE_GND:
            print('%s gated to ground' % t)
            CircuitTree(sys.stdout,c,1).dump_transistor(t.id)
            print()
        if gate.flags & NODE_PWR:
            print('%s gated to power' % t)
            CircuitTree(sys.stdout,c,1).dump_transistor(t.id)
            print()
    '''
    '''
    # find unreferenced transistors
    print()
    (v_node, v_trans) = find_connected_components(c, c.node[103])
    for t in c.trans:
        if not t.id in v_trans:
            print('Unvisited transistor %s' % t)
    for n in c.node:
        if not (n.flags & (NODE_UNDEFINED|NODE_GND|NODE_PWR)) and not n.id in v_node:
            print('Unvisited node %s' % n)
    '''
    all_nodes = set(x.id for x in c.node if not x.flags & (NODE_UNDEFINED|NODE_GND|NODE_PWR))
    groups = 0
    group_max_nodes = 0
    group_max_inputs = 0
    group_max_outputs = 0
    group_type_counts = defaultdict(int)
    print()
    while all_nodes:
        x = all_nodes.pop()
        (v_node, v_trans) = find_connected_components(c, c.node[x], 6)
        flags = ''
        groupid = sorted(v_node)[0]
        # determine input gates and outputs connected to gates
        inputs = set()
        outputs = set()
        for n in v_node:
            inputs.update(c.trans[t].gate for t in c.node[n].c1s)
            inputs.update(c.trans[t].gate for t in c.node[n].c2s)
            if c.node[n].gates:
                outputs.add(n)
        inouts = inputs.intersection(outputs)

        # classify group
        is_pure_op = True
        is_sink = (len(outputs)==0)
        for n in v_node:
            node = c.node[n]
            # if this is an output, but it is not pulled up or down,
            # this contains memory and is not a pure logic element
            if node.gates and not node.flags & (NODE_PULLUP | NODE_PULLDOWN):
                is_pure_op = False

        gtype = 'unk'
        if is_sink:
            gtype = 'sink' # pins and such, no outputs
        elif is_pure_op:
            gtype = 'op'
            if len(v_node) == 1:
                # TODO: check all inputs are GND
                if len(inputs) == 1:
                    gtype = 'inv'
                else:
                    gtype = 'nor'

        show = True
        if show:
            print('Group %04i %s (%i nodes, %i inputs, %i outputs, %i inouts, %s)' % (
                groupid,flags,len(v_node),len(inputs),len(outputs),len(inouts), ['impure', 'pure'][is_pure_op]))
            print('  Inputs: %s' % (' '.join(('%04i'%x) for x in inputs)))
            print('  Outputs: %s' % (' '.join(('%04i'%x) for x in outputs)))
            print('  URI: find=%s' % (','.join(('%i'%x) for x in v_node)))
            for n in v_node:
                nflags = ''
                node = c.node[n]
                if node.flags & NODE_PULLUP:
                    nflags += '+'
                else:
                    nflags += ' '
                if node.flags & NODE_PULLDOWN:
                    nflags += '-'
                else:
                    nflags += ' '
                if node.gates:
                    nflags += 'G'
                else:
                    nflags += ' '
                if n in inputs:
                    nflags += 'I'
                else:
                    nflags += ' '

                c1c2s = []
                for y,x in node.sibs:
                    if x == c.gnd:
                        c1c2s.append('GND ')
                    elif x == c.pwr:
                        c1c2s.append('PWR ')
                    else:
                        c1c2s.append('%04i' % (x))
                if node.name:
                    name = node.name[0:5]
                else:
                    name = ''
                print('  %04i(%-5s) %s %s' % (n,name,nflags,' '.join(c1c2s)))
            print()

        # statistics
        group_max_nodes = max(group_max_nodes, len(v_node))
        group_max_inputs = max(group_max_inputs, len(inputs))
        group_max_outputs = max(group_max_outputs, len(outputs))
        group_type_counts[gtype] += 1

        all_nodes -= v_node
        groups += 1

    print("%i separate groups" % (groups))
    print("of which %i inverters" % (group_type_counts['inv']))
    print("of which %i nor gates" % (group_type_counts['nor']))
    print("of which %i sinks" % (group_type_counts['sink']))
    print("of which %i other pure" % (group_type_counts['op']))
    print("of which %i other impure" % (group_type_counts['unk']))
    print("largest group has %i nodes" % (group_max_nodes))
    print("largest number of inputs is %i" % (group_max_inputs))
    print("largest number of outputs is %i" % (group_max_outputs))

    state_nodes = set(x.id for x in c.node if not x.flags & (NODE_UNDEFINED|NODE_GND|NODE_PWR|NODE_PULLUP|NODE_PULLDOWN))
    print("number of state nodes %i" % (len(state_nodes)))


if __name__ == '__main__':
    main()

# erratum:
#  t2370 connected to node 806, which are connected to nothing else
#  probably meant to be connected to clk1out pin


