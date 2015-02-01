'''
6502 x-ray probing
'''
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
layer_colors = [
        (0.5,0.5,0.75,0.4),
        (1.0,1.0,0,1.0),
        (1.0,0.0,1.0,1.0),
        (0.3,1.0,0.3,1.0), 
        (1.0, 0.3, 0.3,1.0), 
        (0.5,0.1,0.75,1.0), 
        (0.5,0.0,1.0,0.75)]
HITBUFFER_W = 600
HITBUFFER_H = 600
INITIAL_SCALE = 600
MOVE_AMOUNT = 300

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

def draw_segs(cr, seg):
    cr.move_to(seg[1], seg[2])
    for i in range(3, len(seg), 2):
        cr.line_to(seg[i], seg[i+1])
    cr.line_to(seg[1], seg[2])

class SelBox(object):
    def __init__(self, cpt, extents, node):
        (txb,tyb,tw,th,txa,tya) = extents
        self.x1 = txb + cpt[0]
        self.y1 = tyb + cpt[1]
        self.x2 = txb + tw + cpt[0]
        self.y2 = tyb + th + cpt[1]
        self.node = node

    def intersects(self, x, y):
        return self.x1 <= x < self.x2 and self.y1 <= y < self.y2

def show_node_text(cr, node):
    '''Show text and return a selection box'''
    cpt = cr.get_current_point()
    text = '%d ' % node
    cr.show_text(text)
    extents = cr.text_extents(text)
    return SelBox(cpt, extents, node)

class MouseButtons:
    LEFT_BUTTON = 1
    RIGHT_BUTTON = 3


class ChipVisualizer(Gtk.Window):
    def __init__(self, circuit):
        super(ChipVisualizer, self).__init__()
        
        self.width = 1300
        self.height = 600
        self.init_ui()
        self.center = (self.width/2, self.height/2)

        self.c = circuit
        self.hitbuffer_data = None
        self.background = None
        self.scale = INITIAL_SCALE
        self.ofs = [self.scale/2 - self.center[0],self.scale/2 - self.center[1]]
        self.build_hitbuffer()
        self.selected = None
        self.need_background_redraw = False
        self.selection_locked = False
        self.highlighted = None

        self.ibw = 300
        self.ibh = self.height - 10
        self.ibx = self.width - self.ibw - 5
        self.iby = 5
        self.infobox_mapping = []
        
    def init_ui(self):    
        self.darea = Gtk.DrawingArea()
        self.darea.connect("draw", self.on_draw)
        self.darea.set_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.add(self.darea)
        
        self.darea.connect("button-press-event", self.on_button_press)
        self.darea.connect("motion-notify-event", self.on_motion)
        # enter-notify-event
        # leave-notify-event

        self.set_title('6502 X-Ray')
        self.resize(self.width, self.height)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", Gtk.main_quit)
        self.connect("key-press-event", self.on_key_press)
        self.show_all()

    def draw_layer(self, cr, layer):
        for node,polys in self.c.seg.items():
            for seg in polys:
                if seg[0] == layer:
                    draw_segs(cr, seg)

    def draw_selection(self, cr):
        cr.save()
        cr.translate(-self.ofs[0], -self.ofs[1])
        cr.scale(self.scale / grChipSize, -self.scale / grChipSize)
        cr.translate(0, -grChipSize)

        cr.set_source_rgba(0.0,1.0,1.0,1.0)
        for seg in self.c.seg[self.selected]:
            draw_segs(cr, seg)
        cr.fill()

        # local group ("side")
        # mark rest of potential group (c1c2s)
        sel_node = self.c.node[self.selected]
        (v_node, v_trans) = find_connected_components(self.c, sel_node, 6)
        v_node.remove(self.selected)
        cr.set_source_rgba(0.0,0.0,1.0,1.0)
        for node in v_node:
            for seg in self.c.seg[node]:
                draw_segs(cr, seg)
        cr.fill()

        # direct influence ("downstream")
        gates = set()
        for t in sel_node.gates:
            gates.add(self.c.trans[t].c1)
            gates.add(self.c.trans[t].c2)
        gates -= {self.c.gnd, self.c.pwr}

        cr.set_source_rgba(0.0,0.5,1.0,1.0)
        for node in gates:
            for seg in self.c.seg[node]:
                draw_segs(cr, seg)
        cr.fill()

        # influenced by ("upstream")
        gated = set()
        for t in itertools.chain(sel_node.c1s,sel_node.c2s):
            gated.add(self.c.trans[t].gate)
        gated -= {self.c.gnd, self.c.pwr}

        cr.set_source_rgba(0.25,0.25,1.0,1.0)
        for node in gated:
            for seg in self.c.seg[node]:
                draw_segs(cr, seg)
        cr.fill()

        # TODO: add halo/fade
        # http://mxr.mozilla.org/mozilla2.0/source/gfx/thebes/gfxBlur.cpp
        # http://code.google.com/p/infekt/source/browse/trunk/src/lib/cairo_box_blur.cpp
        # TODO:
        # which nodes are pulled-up (red) and which ones are pull-down (green) due to this node
        # direct influenced by
        cr.restore()
        return {'v_node':v_node, 'gates':gates, 'gated':gated}

    def draw_infobox(self, cr, info):
        cr.rectangle(self.ibx, self.iby, self.ibw, self.ibh)
        cr.set_source_rgba(0.025, 0.025, 0.025, 0.95)
        cr.fill()

        cr.select_font_face("Arial",
                  cairo.FONT_SLANT_NORMAL,
                  cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(15)

        infox = self.ibx + 5
        infoy = self.iby + 5 + 15
        ldist = 16
        base_color = (0.7,0.7,0.7)
        mapping = []

        if self.selected is not None:
            sel_node = self.c.node[self.selected]
            cr.move_to(infox, infoy)
            cr.set_source_rgb(0.3, 1.0, 1.0)
            cr.show_text("Node %d " % self.selected)
            if sel_node.name is not None:
                cr.set_source_rgb(base_color[0], base_color[1], base_color[2])
                cr.show_text(sel_node.name)
            infoy += ldist*2
            cr.move_to(infox, infoy)
            if sel_node.flags & NODE_PULLDOWN:
                cr.set_source_rgb(layer_colors[3][0], layer_colors[3][1], layer_colors[3][2])
                cr.show_text("pulldown ")
            if sel_node.flags & NODE_PULLUP:
                cr.set_source_rgb(layer_colors[4][0], layer_colors[4][1], layer_colors[4][2])
                cr.show_text("pullup ")

            infoy += ldist*2
            tb = infoy
            cr.move_to(infox, infoy)
            cr.set_source_rgb(base_color[0], base_color[1], base_color[2])
            cr.show_text("Local group")
            infoy += ldist*1
            for bnode in sorted(info['v_node']):
                cr.move_to(infox, infoy)
                if bnode == self.highlighted:
                    cr.set_source_rgba(0.9,0.9,0.9,1.0)
                else:
                    cr.set_source_rgba(0.0,0.0,1.0,1.0)
                mapping.append(show_node_text(cr, bnode))
                if self.c.node[bnode].name is not None:
                    cr.set_source_rgb(base_color[0], base_color[1], base_color[2])
                    cr.show_text(self.c.node[bnode].name)
                infoy += ldist*1
                if infoy >= (self.iby+self.ibh):
                    break
            yend = infoy

            infoy = tb
            infox += self.ibw/2
            cr.move_to(infox, infoy)
            cr.set_source_rgb(base_color[0], base_color[1], base_color[2])
            cr.show_text("Gates")
            infoy += ldist*1
            cr.move_to(infox, infoy)
            for bnode in sorted(info['gates']):
                cr.move_to(infox, infoy)
                if bnode == self.highlighted:
                    cr.set_source_rgba(0.9,0.9,0.9,1.0)
                else:
                    cr.set_source_rgba(0.0,0.5,1.0,1.0)
                mapping.append(show_node_text(cr, bnode))
                if self.c.node[bnode].name is not None:
                    cr.set_source_rgb(base_color[0], base_color[1], base_color[2])
                    cr.show_text(self.c.node[bnode].name)
                infoy += ldist*1
                if infoy >= (self.iby+self.ibh):
                    break

            if yend < (self.iby+self.ibh):
                infox = self.ibx + 5
                infoy = yend + ldist
                cr.move_to(infox, infoy)
                cr.set_source_rgb(base_color[0], base_color[1], base_color[2])
                cr.show_text("Gated by")
                infoy += ldist*1
                cr.move_to(infox, infoy)
                for bnode in sorted(info['gated']):
                    cr.move_to(infox, infoy)
                    if bnode == self.highlighted:
                        cr.set_source_rgba(0.9,0.9,0.9,1.0)
                    else:
                        cr.set_source_rgba(0.25,0.25,1.0,1.0)
                    mapping.append(show_node_text(cr, bnode))
                    if self.c.node[bnode].name is not None:
                        cr.set_source_rgb(base_color[0], base_color[1], base_color[2])
                        cr.show_text(self.c.node[bnode].name)
                    infoy += ldist*1
                    if infoy >= (self.iby+self.ibh):
                        break
        return mapping

    def draw_highlight(self, cr):
        cr.save()
        cr.translate(-self.ofs[0], -self.ofs[1])
        cr.scale(self.scale / grChipSize, -self.scale / grChipSize)
        cr.translate(0, -grChipSize)

        cr.set_source_rgba(1.0,1.0,1.0,0.25)
        for seg in self.c.seg[self.highlighted]:
            draw_segs(cr, seg)
        cr.fill()
        cr.restore()

    def on_draw(self, wid, cr):
        cr.rectangle(0, 0, self.width, self.height)
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.fill()

        cr.set_line_width(1.0)

        if self.background is None or self.need_background_redraw:
            # Cache background, unless layers or scaling changed
            cr.push_group()
            cr.set_line_width(4.0)
            cr.translate(-self.ofs[0], -self.ofs[1])
            cr.scale(self.scale / grChipSize, -self.scale / grChipSize)
            cr.translate(0, -grChipSize)
            for c in range(6):
                #cr.set_source_rgba(layer_colors[c][0], layer_colors[c][1], layer_colors[c][2], layer_colors[c][3])
                cr.set_source_rgba(0.3,0.3,0.3,0.3)
                self.draw_layer(cr, c)
                if c == 0 or c == 6:
                    cr.fill_preserve()
                    cr.stroke()
                else:
                    cr.fill()
            self.background = cr.pop_group()
            self.need_background_redraw = False

        cr.set_source(self.background)
        cr.rectangle(0, 0, self.width, self.height) #600, 600)
        cr.fill()

        info = None
        if self.selected is not None: # draw selected
            info = self.draw_selection(cr)

        if self.highlighted is not None and self.highlighted is not self.selected: # draw highlight
            self.draw_highlight(cr)
        # Infobox
        self.infobox_mapping = self.draw_infobox(cr, info)

    def build_hitbuffer(self):
        '''
        Make buffer for picking.
        '''
        hitbuffer = cairo.ImageSurface(cairo.FORMAT_ARGB32, HITBUFFER_W, HITBUFFER_H)
        cr = cairo.Context(hitbuffer)
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.rectangle(0, 0, HITBUFFER_W, HITBUFFER_H)
        cr.fill()
        cr.scale(HITBUFFER_W / grChipSize, HITBUFFER_H / grChipSize)

        for node,polys in self.c.seg.items():
            rr = (node & 0xF)/15.0
            gg = ((node>>4) & 0xF)/15.0
            bb = ((node>>8) & 0xF)/15.0
            cr.set_source_rgb(rr,gg,bb)
            for seg in polys:
                cr.move_to(seg[1], seg[2])
                for i in range(3, len(seg), 2):
                    cr.line_to(seg[i], seg[i+1])
                cr.line_to(seg[1], seg[2])
            cr.fill()
        hitbuffer.flush()
        #hitbuffer.write_to_png('/tmp/boe.png')
        self.hitbuffer_data = hitbuffer.get_data()

    def node_from_xy(self, x, y):
        '''
        Chip coordinates to node number.
        '''
        x = int(x * HITBUFFER_W / grChipSize)
        y = int(y * HITBUFFER_H / grChipSize)
        if x < 0 or y < 0 or x >= HITBUFFER_W or y >= HITBUFFER_H:
            return None
        ofs = y * HITBUFFER_H + x
        rr = ord(self.hitbuffer_data[ofs*4+2]) >> 4
        gg = ord(self.hitbuffer_data[ofs*4+1]) >> 4
        bb = ord(self.hitbuffer_data[ofs*4+0]) >> 4
        node = rr | (gg << 4) | (bb << 8)
        if node == 4095:
            return None
        return node

    def node_from_event(self, e):
        if e.x >= self.ibx and e.y >= self.iby and e.x < (self.ibx+self.ibw) and e.y < (self.iby + self.ibh):
            for box in self.infobox_mapping:
                if box.intersects(e.x,e.y):
                    return box.node
            return None # infobox...
        # transpose e.x and e.y to chip coordinate
        node = self.node_from_xy((e.x + self.ofs[0]) / self.scale * grChipSize, grChipSize - (e.y + self.ofs[1]) / self.scale * grChipSize)
        if node == self.c.pwr or node == self.c.gnd: # don't select power or ground
            node = None
        return node

    def on_motion(self, w, e):
        if self.hitbuffer_data is not None:
            node = self.node_from_event(e)
            if self.selection_locked: # if selection locked, only update highlight
                if node is not self.highlighted:
                    self.highlighted = node
                    self.darea.queue_draw()
            else:
                if node is not self.selected:
                    self.selected = node
                    self.darea.queue_draw()

    def on_button_press(self, w, e):
        if e.type == Gdk.EventType.BUTTON_PRESS \
            and e.button == MouseButtons.LEFT_BUTTON:
            node = self.node_from_event(e)
            if node is not None:
                self.selected = node
                self.selection_locked = True
            self.darea.queue_draw()           
            
        if e.type == Gdk.EventType.BUTTON_PRESS \
            and e.button == MouseButtons.RIGHT_BUTTON:
            self.selection_locked = False
            self.selected = None
            self.highlighted = None
            self.darea.queue_draw()
        return True

    def on_key_press(self, w, e):
        if e.string == '+' or e.string == '>':
            self.scale *= 2
            self.ofs[0] = (self.ofs[0] + self.center[0]) * 2 - self.center[0]
            self.ofs[1] = (self.ofs[1] + self.center[1]) * 2 - self.center[1]
            self.need_background_redraw = True
            self.darea.queue_draw()
        if e.string == '-' or e.string == '<':
            self.scale /= 2
            self.ofs[0] = (self.ofs[0] + self.center[0]) / 2 - self.center[0]
            self.ofs[1] = (self.ofs[1] + self.center[1]) / 2 - self.center[1]
            self.need_background_redraw = True
            self.darea.queue_draw()
        if e.string == '0':
            self.scale = INITIAL_SCALE
            self.need_background_redraw = True
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_Left:
            self.ofs[0] -= MOVE_AMOUNT
            self.need_background_redraw = True
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_Right:
            self.ofs[0] += MOVE_AMOUNT
            self.need_background_redraw = True
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_Up:
            self.ofs[1] -= MOVE_AMOUNT
            self.need_background_redraw = True
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_Down:
            self.ofs[1] += MOVE_AMOUNT
            self.need_background_redraw = True
            self.darea.queue_draw()

        return True


def main():
    c = load_circuit()
    app = ChipVisualizer(c)
    Gtk.main()
        
if __name__ == "__main__":    
    main()


