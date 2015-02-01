from circuit import Node, load_circuit, NODE_PULLUP, NODE_PULLDOWN, NODE_UNDEFINED, NODE_GND, NODE_PWR, Transistor

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
    def count(self):
        return sum(c.count() for c in self.children)

class OrNode(ExprNode):
    def __init__(self, children):
        self.children = children
    def __repr__(self):
        return '(' + ('||'.join(repr(x) for x in self.children)) + ')'
    def count(self):
        return sum(c.count() for c in self.children)

class NodeValNode(ExprNode):
    def __init__(self, id):
        self.id = id
    def __repr__(self):
        return 'get_nodes_value(state, %i)' % (self.id)
    def count(self):
        return 1

class InvertNode(ExprNode):
    def __init__(self, c):
        self.c = c
    def __repr__(self):
        return '!' + repr(self.c)
    def count(self):
        return 1 + self.c.count()

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

class NodeGroup(object):
    def __init__(self, id):
        self.id = id

def extract_groups(c):
    all_nodes = set(x.id for x in c.node if not x.flags & (NODE_UNDEFINED|NODE_GND|NODE_PWR))
    groups = []
    group_by_node = [None]*len(c.node)
    while all_nodes:
        x = all_nodes.pop()
        (v_node, v_trans) = find_connected_components(c, c.node[x], 6)
        groupid = sorted(v_node)[0]
        # determine input gates and outputs connected to gates
        inputs = set()
        outputs = set()
        for n in v_node:
            inputs.update(c.trans[t].gate for t in c.node[n].c1s)
            inputs.update(c.trans[t].gate for t in c.node[n].c2s)
            if c.node[n].gates:
                outputs.add(n)

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

        # pure
        expr = None
        expr_out = None
        if is_pure_op and len(outputs)==1:
            # build expression
            expr_out = list(outputs)[0]
            expr = InvertNode(make_expr(c, expr_out, -1))

        group = NodeGroup(groupid)
        group.inputs = inputs
        group.outputs = outputs
        group.is_pure_op = is_pure_op
        group.is_sink = is_sink
        group.is_source = is_source
        group.gtype = gtype
        group.nodes = v_node
        group.expr = expr
        group.expr_out = expr_out
        for node in v_node:
            group_by_node[node] = group
        groups.append(group)
        all_nodes -= v_node

    for i,x in enumerate(group_by_node):
        c.node[i].group = x

    return groups
