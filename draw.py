from __future__ import division, print_function
import sys
from collections import defaultdict
from gi.repository import Gtk, Gdk
import itertools
import cairo, math
import json
import sys
from collections import defaultdict

NODE_PULLUP = 1
NODE_PULLDOWN = 2
NODE_GND = 4
NODE_PWR = 8
NODE_UNDEFINED = 16

TRANS_DUPLICATE = 1

grChipSize = 10000
layer_names = ['metal', 'switched diffusion', 'inputdiode', 'grounded diffusion', 'powered diffusion', 'polysilicon']
layer_colors = [(0.5,0.5,0.75,0.4),(1.0,1.0,0,1.0),(1.0,0.0,1.0,1.0),(0.3,1.0,0.3,1.0), (1.0, 0.3, 0.3,1.0), (0.5,0.1,0.75,1.0), (0.5,0.0,1.0,0.75)]

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

class MouseButtons:
    LEFT_BUTTON = 1
    RIGHT_BUTTON = 3

class Example(Gtk.Window):
    def __init__(self, circuit):
        super(Example, self).__init__()
        
        self.width = 1300
        self.height = 600
        self.init_ui()

        self.c = circuit
        
    def init_ui(self):    
        self.darea = Gtk.DrawingArea()
        self.darea.connect("draw", self.on_draw)
        self.darea.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)        
        self.add(self.darea)
        
        self.darea.connect("button-press-event", self.on_button_press)

        self.set_title('6502')
        self.resize(self.width, self.height)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", Gtk.main_quit)
        self.show_all()

    def draw_layer(self, cr, layer):
        for node,polys in self.c.seg.items():
            for seg in polys:
                if seg[0] == layer:
                    cr.move_to(seg[1], seg[2])
                    for i in range(3, len(seg), 2):
                        cr.line_to(seg[i], seg[i+1])
                    cr.line_to(seg[1], seg[2])

    def on_draw(self, wid, cr):
        cr.rectangle(0, 0, self.width, self.height)
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.fill()

        cr.set_line_width(1.0)

        cr.save()
        cr.scale(600.0 / grChipSize, -600.0 / grChipSize)
        cr.translate(0, -grChipSize)
        for c in range(6):
            cr.set_source_rgba(layer_colors[c][0], layer_colors[c][1], layer_colors[c][2], layer_colors[c][3])
            self.draw_layer(cr, c)
            if c == 0 or c == 6:
                cr.fill_preserve()
                cr.stroke()
            else:
                cr.fill()
        cr.restore()

                         
    def on_button_press(self, w, e):
        
        if e.type == Gdk.EventType.BUTTON_PRESS \
            and e.button == MouseButtons.LEFT_BUTTON:
           pass
            
        if e.type == Gdk.EventType.BUTTON_PRESS \
            and e.button == MouseButtons.RIGHT_BUTTON:
            
            self.darea.queue_draw()           

def main():
    c = load_circuit()
    app = Example(c)
    Gtk.main()
        
if __name__ == "__main__":    
    main()


