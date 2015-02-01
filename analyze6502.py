# coding: utf-8
'''
Convert 6502 data from json files to our own
data format.
'''
from __future__ import division, print_function
import sys
from collections import defaultdict
from circuit import load_circuit,Node,Transistor,NODE_PULLUP,NODE_PULLDOWN,NODE_GND,NODE_PWR,NODE_UNDEFINED

layer_names = ['metal', 'switched diffusion', 'inputdiode', 'grounded diffusion', 'powered diffusion', 'polysilicon']

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

class ExprNode(object):
    pass

class AndNode(ExprNode):
    def __init__(self, children):
        self.children = children
    def __repr__(self):
        return '(' + ('&&'.join(repr(x) for x in self.children)) + ')'

class OrNode(ExprNode):
    def __init__(self, children):
        self.children = children
    def __repr__(self):
        return '(' + ('||'.join(repr(x) for x in self.children)) + ')'

class NodeValNode(ExprNode):
    def __init__(self, id):
        self.id = id
    def __repr__(self):
        return 'get_nodes_value(state, %i)' % (self.id)

class InvertNode(ExprNode):
    def __init__(self, c):
        self.c = c
    def __repr__(self):
        return '!' + repr(self.c)

def make_expr(c, out, parent):
    terms = []
    node = c.node[out]
    for y,x in node.sibs:
        if x == parent:
            continue # backref
        elif x == c.gnd:
            terms.append(NodeValNode(y))
        elif x == c.pwr:
            assert(0)
        else:
            terms.append(AndNode([NodeValNode(y), make_expr(c, x, out)]))
    return OrNode(terms)

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
    to_compute = defaultdict(int)
    to_compute_by_group = defaultdict(int)
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
        is_source = (len(inputs)==0)
        for n in v_node:
            node = c.node[n]
            # if this is an output, but it is not pulled up or down,
            # this contains memory and is not a pure logic element
            if node.gates and not node.flags & (NODE_PULLUP | NODE_PULLDOWN):
                is_pure_op = False

        gtype = 'unk'
        if is_source:
            gtype = 'source' # pins and such, no inputs
        elif is_sink:
            gtype = 'sink' # pins and such, no outputs
        elif is_pure_op:
            gtype = 'op'
            if len(v_node) == 1:
                # TODO: check all inputs are GND
                if len(inputs) == 1:
                    gtype = 'inv'
                else:
                    gtype = 'nor'

        show = False
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
                        c1c2s.append('GND[%04i] '% (y))
                    elif x == c.pwr:
                        c1c2s.append('PWR[%04i] '% (y))
                    else:
                        c1c2s.append('%04i[%04i]' % (x,y))
                if node.name:
                    name = node.name[0:5]
                else:
                    name = ''
                print('  %04i(%-5s) %s %s' % (n,name,nflags,' '.join(c1c2s)))
            print()

        # pure
        if is_pure_op and len(outputs)==1:
            # build expression
            out = list(outputs)[0]
            e = InvertNode(make_expr(c, out, -1))
            print('case %i: return %s; break;' % (out, e))
            to_compute[out] |= 1
            for x in v_node:
                to_compute_by_group[x] = out
                to_compute[x] |= 4
        else:
            for x in v_node:
                to_compute[x] |= 2

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
    print("of which %i sources" % (group_type_counts['source']))
    print("of which %i other pure" % (group_type_counts['op']))
    print("of which %i other impure" % (group_type_counts['unk']))
    print("largest group has %i nodes" % (group_max_nodes))
    print("largest number of inputs is %i" % (group_max_inputs))
    print("largest number of outputs is %i" % (group_max_outputs))

    state_nodes = set(x.id for x in c.node if not x.flags & (NODE_UNDEFINED|NODE_GND|NODE_PWR|NODE_PULLUP|NODE_PULLDOWN))
    print("number of state nodes %i" % (len(state_nodes)))

    sout = [to_compute[n] for n in range(len(c.node))]
    print('const char to_simulate[%i] = {%s};' %
            (len(c.node), (','.join(str(x) for x in sout))))

    sout = [to_compute_by_group[n] for n in range(len(c.node))]
    print('const int to_compute_by_group[%i] = {%s};' %
            (len(c.node), (','.join(str(x) for x in sout))))

    # TODO: could combine multiple digital groups if their result is not used outside it,
    # and not an external pin

if __name__ == '__main__':
    main()

# erratum:
#  t2370 connected to node 806, which are connected to nothing else
#  probably meant to be connected to clk1out pin


