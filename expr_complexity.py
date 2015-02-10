#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
Output relative expression complexity overlay data.
'''
from __future__ import division, print_function
import sys
from collections import defaultdict
import itertools, operator
import sys
from collections import defaultdict
from circuit import Node, load_circuit, NODE_PULLUP, NODE_PULLDOWN, NODE_UNDEFINED, NODE_GND, NODE_PWR, Transistor
from node_group import extract_groups, AndNode, OrNode, NodeValNode, InvertNode
import json

def main():
    c = load_circuit()
    extract_groups(c)

    values = []
    for node in c.node:
        if node.group is not None and node.group.expr is not None:
            expr = node.group.expr
            cnt = expr.count()
            value = cnt*0.1
        else:
            value = 0
        values.append(value)

    obj = {
        'title': 'Expression complexity',
        'values': values
    }

    with open('expr_complexity.json', 'wb') as f:
        json.dump(obj, f)

if __name__ == "__main__":    
    main()


