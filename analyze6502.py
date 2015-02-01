# coding: utf-8
'''
Convert 6502 data from json files to our own
data format.
'''
from __future__ import division, print_function
import sys
from collections import defaultdict
from circuit import load_circuit,Node,Transistor,NODE_PULLUP,NODE_PULLDOWN,NODE_GND,NODE_PWR,NODE_UNDEFINED
from node_group import extract_groups

layer_names = ['metal', 'switched diffusion', 'inputdiode', 'grounded diffusion', 'powered diffusion', 'polysilicon']

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

    groups = extract_groups(c)

    group_type_counts = defaultdict(int)
    group_max_nodes = 0
    group_max_inputs = 0
    group_max_outputs = 0
    to_compute = [0]*len(c.node)
    to_compute_by_group = [-1]*len(c.node)
    for group in groups:
        group_type_counts[group.gtype] += 1
        group_max_nodes = max(group_max_nodes, len(group.nodes))
        group_max_outputs = max(group_max_outputs, len(group.outputs))
        group_max_inputs = max(group_max_inputs, len(group.inputs))
        if group.expr_out is not None:
            print('case %i: return %s; break;' % (group.expr_out, group.expr))
            to_compute[group.expr_out] |= 1
            for x in group.nodes:
                to_compute_by_group[x] = group.expr_out
                to_compute[x] |= 4
        else:
            for x in group.nodes:
                to_compute[x] |= 2

    for group in groups:
        show = False
        if show:
            inouts = group.inputs.intersection(group.outputs)
            print('Group %04i (%i nodes, %i inputs, %i outputs, %i inouts, %s)' % (
                group.id,len(group.nodes),len(group.inputs),len(group.outputs),len(inouts), ['impure', 'pure'][group.is_pure_op]))
            print('  Inputs: %s' % (' '.join(('%04i'%x) for x in group.inputs)))
            print('  Outputs: %s' % (' '.join(('%04i'%x) for x in group.outputs)))
            print('  URI: find=%s' % (','.join(('%i'%x) for x in group.nodes)))
            for n in group.nodes:
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
                if n in group.inputs:
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

    print("%i separate groups" % (len(groups)))
    print("of which %i inverters" % (group_type_counts['inv']))
    print("of which %i nor gates" % (group_type_counts['nor']))
    print("of which %i sinks" % (group_type_counts['sink']))
    print("of which %i sources" % (group_type_counts['source']))
    print("of which %i other pure" % (group_type_counts['op']))
    print("of which %i other impure" % (group_type_counts['unk']))
    print("largest group has %i nodes" % (group_max_nodes))
    print("largest number of inputs is %i" % (group_max_inputs))
    print("largest number of outputs is %i" % (group_max_outputs))

    print('const char to_simulate[%i] = {%s};' %
            (len(c.node), (','.join(str(x) for x in to_compute))))

    print('const short to_compute_by_group[%i] = {%s};' %
            (len(c.node), (','.join(str(x) for x in to_compute_by_group))))

    # TODO: could combine multiple digital groups if their result is not used outside it,
    # and not an external pin

if __name__ == '__main__':
    main()

# erratum:
#  t2370 connected to node 806, which are connected to nothing else
#  probably meant to be connected to clk1out pin


