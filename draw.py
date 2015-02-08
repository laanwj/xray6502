#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
6502 x-ray probing
'''
from __future__ import division, print_function
import sys
from collections import defaultdict
from gi.repository import Gtk, Gdk
import itertools, operator
import cairo, math
import sys
from collections import defaultdict
from circuit import Node, load_circuit, NODE_PULLUP, NODE_PULLDOWN, NODE_UNDEFINED, NODE_GND, NODE_PWR, Transistor
from node_group import extract_groups, AndNode, OrNode, NodeValNode, InvertNode

grChipSize = 10000
layer_names = ['metal', 'switched diffusion', 'inputdiode', 'grounded diffusion', 'powered diffusion', 'polysilicon']
NUM_LAYERS = 6
layer_colors = [
        (0.5, 0.5, 0.75,0.4),
        (1.0, 1.0, 0,   1.0),
        (1.0, 0.0, 1.0, 1.0),
        (0.3, 1.0, 0.3, 1.0), 
        (1.0, 0.3, 0.3, 1.0), 
        (0.5, 0.1, 0.75,1.0), 
        (0.5, 0.0, 1.0, 0.75)]
HITBUFFER_W = 600
HITBUFFER_H = 600
INITIAL_SCALE = 600
MOVE_AMOUNT = 200
# colors for tag bits
tag_bit_colors = [
(1.0,0.0,0.0), # red
(1.0,0.5,0.0), # orange
(1.0,1.0,0.0), # yellow
(0.0,1.0,0.0), # green
(0.0,1.0,1.0), # cyan
(0.0,0.5,1.0),
(0.0,0.0,1.0), # blue
#(0.5,0.0,1.0), #
(1.0,0.0,1.0), # purple
#(1.0,0.0,0.5), #
]

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

class MouseButtons:
    LEFT_BUTTON = 1
    RIGHT_BUTTON = 3


class ChipVisualizer(Gtk.Window):
    def __init__(self, circuit, overlay_info, frames):
        super(ChipVisualizer, self).__init__()
        self.width = 1300
        self.height = 600
        self.center = None

        self.c = circuit
        self.overlay_info = overlay_info
        self.frames = frames
        self.frame = 0
        self.cur_overlay = None
        self.hitbuffer_data = None
        self.background = None
        self.scale = INITIAL_SCALE
        self.build_hitbuffer()
        self.selected = None
        self.selection_locked = False
        self.highlighted = None
        self.history = []
        self.show_extrasel = False

        self.ibw = None
        self.ibh = None
        self.ibx = None
        self.iby = None
        self.infobox_mapping = []
        self.infobox_tab = 0
        self.infobox_tabs = 2

        # sort segment per layer, for background drawing
        self.cached_layer_path = None
        self.segs_by_layer = [[] for x in range(NUM_LAYERS)]
        for node,polys in self.c.seg.items():
            for seg in polys:
                self.segs_by_layer[seg[0]].append(seg)

        self.init_ui()
        self.set_sizes(self.width, self.height)
        self.ofs = [self.scale/2 - self.center[0],self.scale/2 - self.center[1]]
        
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
        self.connect("configure-event", self.on_configure_event)
        self.show_all()

    def perform_transformation(self, cr):
        '''
        Perform transformation for rendering chip polygons.
        '''
        cr.translate(-self.ofs[0], -self.ofs[1])
        cr.scale(self.scale / grChipSize, -self.scale / grChipSize)
        cr.translate(0, -grChipSize)

    def draw_background(self, cr):
        '''Draw chip background.
        For performance reasons, the background is cached on two levels: 
        - paths for drawing each layer are cached in cairo,
        - and the finished image ("group") is cached.
        '''
        cr.push_group()
        cr.set_line_width(4.0)
        self.perform_transformation(cr)
        if self.cached_layer_path is None:
            self.cached_layer_path = [None] * NUM_LAYERS
            for c in range(NUM_LAYERS):
                for seg in self.segs_by_layer[c]:
                    draw_segs(cr, seg)
                self.cached_layer_path[c] = cr.copy_path()
                cr.new_path()

        cr.set_operator(cairo.OPERATOR_ADD)
        for c in range(NUM_LAYERS):
            #cr.set_source_rgba(*layer_colors[c])
            # introduce a slight difference in intensity per layer, to
            # make it possible to distinguish structures on different layers
            x = 0.07 + 0.03 * c / (NUM_LAYERS-1)
            cr.set_source_rgba(x,x,x,1.0)
            cr.append_path(self.cached_layer_path[c])
            if c == 0 or c == 6:
                cr.fill_preserve()
                cr.stroke()
            else:
                cr.fill()
        return cr.pop_group()

    def draw_selection(self, cr, node_attr):
        cr.save()
        self.perform_transformation(cr)

        node_attr[self.selected]['color'] = (0.0,1.0,1.0)

        sel_node = self.c.node[self.selected]

        v_node = set()
        gated = set()
        peers = set()
        for t in sel_node.c1s:
            v_node.add(self.c.trans[t].c2)
            gated.add(self.c.trans[t].gate)
            peers.add((self.c.trans[t].gate, self.c.trans[t].c2))
        for t in sel_node.c2s:
            v_node.add(self.c.trans[t].c1)
            gated.add(self.c.trans[t].gate)
            peers.add((self.c.trans[t].gate, self.c.trans[t].c1))
        v_node -= {self.selected, self.c.pwr, self.c.gnd}
        gated -= {self.selected, self.c.pwr, self.c.gnd}

        gates = set()
        for t in sel_node.gates:
            gates.add(self.c.trans[t].c1)
            gates.add(self.c.trans[t].c2)
        gates -= {self.c.gnd, self.c.pwr}

        if self.show_extrasel:
            # local group ("side")
            for node in v_node:
                node_attr[node]['color'] = (0.0,0.0,1.0)
            # direct influence ("downstream")
            for node in gates:
                node_attr[node]['color'] = (0.0,0.5,1.0)
            # influenced by ("upstream")
            for node in gated:
                node_attr[node]['color'] = (0.25,0.25,1.0)

        # TODO: add halo/fade/animation
        # http://mxr.mozilla.org/mozilla2.0/source/gfx/thebes/gfxBlur.cpp
        # http://code.google.com/p/infekt/source/browse/trunk/src/lib/cairo_box_blur.cpp
        cr.restore()
        return {'v_node':v_node, 'gates':gates, 'gated':gated, 'peers':peers, 'extraflags':[]}

    def show_node_text(self, cr, node):
        '''Show text and return a selection box'''
        cpt = cr.get_current_point()
        if node == self.c.pwr:
            cr.set_source_rgba(*layer_colors[4])
            text = 'PWR '
            node = None
        elif node == self.c.gnd:
            cr.set_source_rgba(*layer_colors[3])
            text = 'GND '
            node = None
        else:
            if node in self.node_attr and 'color' in  self.node_attr[node]:
                cr.set_source_rgb(*self.node_attr[node]['color'])
            else:
                cr.set_source_rgb(0.25, 0.25, 0.25)
            text = '%d ' % node
        cr.show_text(text)
        extents = cr.text_extents(text)
        return SelBox(cpt, extents, node)

    def draw_infobox(self, cr, info, extra_sel_flags):
        '''Draw infobox for node mode'''
        cr.rectangle(self.ibx, self.iby, self.ibw, self.ibh)
        cr.set_source_rgba(0.025, 0.025, 0.025, 0.93)
        cr.fill()

        cr.select_font_face("Arial",
                  cairo.FONT_SLANT_NORMAL,
                  cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(15)

        infox = self.ibx + 5
        infoy = self.iby + 5 + 15
        ldist = 16
        base_color = (0.7,0.7,0.7)
        hdr_color = (0.4,0.4,0.4)
        mapping = []

        if self.selected is not None:
            sel_node = self.c.node[self.selected]
            cr.move_to(infox, infoy)
            cr.set_source_rgb(0.3, 1.0, 1.0)
            cr.show_text("Node ")
            mapping.append(self.show_node_text(cr, self.selected))
            if sel_node.name is not None:
                cr.set_source_rgb(*base_color)
                cr.show_text(sel_node.name + ' ')

            flags = []
            if sel_node.flags & NODE_PULLDOWN:
                flags.append((layer_colors[3], '-'))
            if sel_node.flags & NODE_PULLUP:
                flags.append((layer_colors[4], '+'))
            flags += extra_sel_flags

            for fc,fs in flags:
                cr.set_source_rgba(*fc)
                cr.show_text(fs + ' ')

            infoy += ldist*1.5
            tb = infoy
            cr.set_source_rgb(*hdr_color)
            cr.move_to(infox, infoy)
            cr.show_text('Gate ...........................')
            cr.move_to(infox + self.ibw/2, infoy)
            cr.show_text('C1C2')
            infoy += ldist*1
            for (gnode,bnode) in sorted(info['peers']):
                cr.move_to(infox, infoy)
                mapping.append(self.show_node_text(cr, gnode))
                if self.c.node[gnode].name is not None:
                    cr.set_source_rgb(*base_color)
                    cr.show_text(self.c.node[gnode].name)

                cr.move_to(infox+self.ibw/2, infoy)
                mapping.append(self.show_node_text(cr, bnode))
                if self.c.node[bnode].name is not None:
                    cr.set_source_rgb(*base_color)
                    cr.show_text(self.c.node[bnode].name)

                infoy += ldist*1
                if infoy >= (self.iby+self.ibh):
                    break

            infoy += ldist*1
            cr.move_to(infox, infoy)
            cr.set_source_rgb(hdr_color[0], hdr_color[1], hdr_color[2])
            cr.show_text("Gated")
            infoy += ldist*1
            cr.move_to(infox, infoy)
            for bnode in sorted(info['gates']):
                cr.move_to(infox, infoy)
                mapping.append(self.show_node_text(cr, bnode))
                if self.c.node[bnode].name is not None:
                    cr.set_source_rgb(*base_color)
                    cr.show_text(self.c.node[bnode].name)
                infoy += ldist*1
                if infoy >= (self.iby+self.ibh):
                    break
        return mapping

    def draw_infobox_group(self, cr, info):
        '''Draw infobox for group mode'''
        cr.rectangle(self.ibx, self.iby, self.ibw, self.ibh)
        cr.set_source_rgba(0.025, 0.025, 0.025, 0.93)
        cr.fill()

        cr.select_font_face("Arial",
                  cairo.FONT_SLANT_NORMAL,
                  cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(15)

        infox = self.ibx + 5
        infoy = self.iby + 5 + 15
        ldist = 16
        base_color = (0.7,0.7,0.7)
        hdr_color = (0.4,0.4,0.4)
        mapping = []

        if self.selected is None:
            return mapping
        sel_node = self.c.node[self.selected]
        if sel_node.group is None:
            return mapping
        group = sel_node.group
        cr.move_to(infox, infoy)
        cr.set_source_rgb(0.3, 1.0, 1.0)
        cr.show_text("Group ")
        mapping.append(self.show_node_text(cr, group.id))

        infoy += ldist*1.5
        tb = infoy
        cr.move_to(infox, infoy)

        for node in group.nodes:
            cr.move_to(infox, infoy)
            mapping.append(self.show_node_text(cr, node))
            if self.c.node[node].name is not None:
                cr.set_source_rgb(*base_color)
                cr.show_text(self.c.node[node].name)

            infoy += ldist*1
            if infoy >= (self.iby+self.ibh):
                break
        
        infoy += ldist*1
        cr.move_to(infox, infoy)
        cr.set_source_rgb(hdr_color[0], hdr_color[1], hdr_color[2])
        cr.show_text("Inputs")
        infoy += ldist*1

        if group.expr is None:
            for node in group.inputs:
                cr.move_to(infox, infoy)
                mapping.append(self.show_node_text(cr, node))
                if self.c.node[node].name is not None:
                    cr.set_source_rgb(*base_color)
                    cr.show_text(self.c.node[node].name)

                infoy += ldist*1
                if infoy >= (self.iby+self.ibh):
                    break
        else:
            _infoy = [infoy]
            INDENT = 15
            div = 0.35
            m1 = 2
            m2 = 2
            def draw_expr(cr,expr,depth,dinfo):
                cr.set_source_rgb(*base_color)
                for x in range(0, depth-1):
                    if dinfo[x]:
                        cr.move_to(infox + x*INDENT + m1, _infoy[0]-ldist)
                        cr.line_to(infox + x*INDENT + m1, _infoy[0])
                cr.stroke()

                cr.move_to(infox + depth*INDENT, _infoy[0])
                cr.set_source_rgb(*base_color)
                if isinstance(expr, AndNode):
                    cr.show_text("and") # alt: U2227
                elif isinstance(expr, OrNode):
                    cr.show_text("or") # alt: U2228
                elif isinstance(expr, InvertNode):
                    cr.show_text("not") # alt: U00AC
                elif isinstance(expr, NodeValNode):
                    mapping.append(self.show_node_text(cr, expr.id))
                    if self.c.node[expr.id].name is not None:
                        cr.set_source_rgb(*base_color)
                        cr.show_text(self.c.node[expr.id].name)
                _infoy[0] += ldist

                for i, e in enumerate(expr.children):
                    cr.set_source_rgba(0.4,0.4,0.4,1.0)
                    if i != 0:
                        cr.move_to(infox + depth*INDENT + m1, _infoy[0]-ldist)
                        cr.line_to(infox + depth*INDENT + m1, _infoy[0]-ldist*div)
                    else: # link to parent
                        cr.move_to(infox + depth*INDENT + m1, _infoy[0]-ldist*0.75)
                        cr.line_to(infox + depth*INDENT + m1, _infoy[0]-ldist*div)
                    if i != len(expr.children)-1:
                        cr.move_to(infox + depth*INDENT + m1, _infoy[0]-ldist*div)
                        cr.line_to(infox + depth*INDENT + m1, _infoy[0])
                    cr.move_to(infox + depth*INDENT + m1, _infoy[0]-ldist*div)
                    cr.line_to(infox + depth*INDENT + INDENT - m2, _infoy[0]-ldist*div)
                    cr.stroke()
                    draw_expr(cr,e,depth+1, dinfo + [i!=len(expr.children)-1])

            draw_expr(cr, group.expr, 0, [])
            infoy = _infoy[0]

        infoy += ldist*1
        cr.move_to(infox, infoy)
        cr.set_source_rgb(hdr_color[0], hdr_color[1], hdr_color[2])
        cr.show_text("Gated")
        infoy += ldist*1
        cr.move_to(infox, infoy)
        for bnode in group.dependents:
            cr.move_to(infox, infoy)
            mapping.append(self.show_node_text(cr, bnode))
            if self.c.node[bnode].name is not None:
                cr.set_source_rgb(*base_color)
                cr.show_text(self.c.node[bnode].name)
            infoy += ldist*1
            if infoy >= (self.iby+self.ibh):
                break

        return mapping

    def draw_highlight(self, cr, node_attr):
        cr.save()
        self.perform_transformation(cr)

        cr.set_source_rgba(1.0,1.0,1.0,0.4)
        for seg in self.c.seg[self.highlighted]:
            draw_segs(cr, seg)
        cr.fill()
        cr.restore()

        node_attr[self.highlighted]['color'] = (0.9,0.9,0.9)

    def draw_frames(self, cr, node_attr, extra_sel_flags):
        d = self.frames[self.frame]
        for i,tag in enumerate(d['tags']):
            if tag != 0:
                color = (0,0,0)
                numset = 0
                for bit,c in enumerate(tag_bit_colors):
                    if tag & (1<<bit):
                        color = c
                        numset += 1
                if numset > 1:
                    color = (0.7,0.7,0.7) # mixing...

                node_attr[i]['color'] = color

        cr.select_font_face("Arial",
                  cairo.FONT_SLANT_NORMAL,
                  cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(15)
        cr.move_to(10, self.height - 20)
        cr.set_source_rgb(1.0,1.0,1.0)
        cr.show_text('Cycle: %i ' % d['cycle'])
        cr.show_text('PC: %04x' % d['pc'])

        if self.selected is not None:
            tag = d['tags'][self.selected]
            for bit,color in enumerate(tag_bit_colors):
                if tag & (1<<bit):
                    extra_sel_flags.append((color, str(bit)))

    def on_draw(self, wid, cr):
        cr.rectangle(0, 0, self.width, self.height)
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.fill()

        cr.set_line_width(1.0)

        if self.background is None:
            # Cache background, unless layers or scaling changed
            self.background = self.draw_background(cr)

        cr.set_source(self.background)
        cr.rectangle(0, 0, self.width, self.height) #600, 600)
        cr.fill()

        # display overlay, for per-node scalar visualization
        if self.cur_overlay is not None:
            cr.save()
            self.perform_transformation(cr)
            for i,value in enumerate(self.overlay_info[self.cur_overlay][1]):
                if value != 0:
                    cr.set_source_rgba(value,value,0.0,1.0)
                    for seg in self.c.seg[i]:
                        draw_segs(cr, seg)
                    cr.fill()
            cr.restore()

        self.node_attr = defaultdict(dict)
        extra_sel_flags = []
        # display animation frames for dataflow analysis
        if self.frames:
            self.draw_frames(cr, self.node_attr, extra_sel_flags)

        info = None
        if self.selected is not None: # draw selected
            info = self.draw_selection(cr, self.node_attr)

        # draw highlighted segments
        for i,attr in self.node_attr.iteritems():
            cr.save()
            self.perform_transformation(cr)
            if 'color' in attr:
                cr.set_source_rgb(*attr['color'])
                for seg in self.c.seg[i]:
                    draw_segs(cr, seg)
                cr.fill()
            cr.restore()

        if self.highlighted is not None:
            self.draw_highlight(cr, self.node_attr)

        # Infobox
        if self.infobox_tab == 0:
            self.infobox_mapping = self.draw_infobox(cr, info, extra_sel_flags)
        elif self.infobox_tab == 1:
            self.infobox_mapping = self.draw_infobox_group(cr, info)

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
            if node in {self.c.gnd, self.c.pwr}:
                continue # we don't want to select gnd and pwr, so don't make them end up in the hitbuffer
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
        return self.node_from_xy((e.x + self.ofs[0]) / self.scale * grChipSize, grChipSize - (e.y + self.ofs[1]) / self.scale * grChipSize)

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
                self.history.append(self.selected)
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
            self.background = None
            self.darea.queue_draw()
        if e.string == '-' or e.string == '<':
            self.scale /= 2
            self.ofs[0] = (self.ofs[0] + self.center[0]) / 2 - self.center[0]
            self.ofs[1] = (self.ofs[1] + self.center[1]) / 2 - self.center[1]
            self.background = None
            self.darea.queue_draw()
        if e.string == '0':
            self.scale = INITIAL_SCALE
            self.background = None
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_Left:
            self.ofs[0] -= MOVE_AMOUNT
            self.background = None
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_Right:
            self.ofs[0] += MOVE_AMOUNT
            self.background = None
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_Up:
            self.ofs[1] -= MOVE_AMOUNT
            self.background = None
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_Down:
            self.ofs[1] += MOVE_AMOUNT
            self.background = None
            self.darea.queue_draw()
        if e.string == 'n': # toggle infobox mode
            self.infobox_tab = (self.infobox_tab + 1) % self.infobox_tabs
            self.darea.queue_draw()
        if e.string == ',' and self.frames:
            self.frame -= 1
            if self.frame < 0:
                self.frame = len(self.frames)-1
            self.darea.queue_draw()
        if e.string == '.' and self.frames:
            self.frame += 1
            if self.frame >= len(self.frames):
                self.frame = 0
            self.darea.queue_draw()
        if e.string == 'x': # show upstream/downstream links for selected node
            self.show_extrasel = not self.show_extrasel
            self.darea.queue_draw()
        if e.keyval == Gdk.KEY_BackSpace:
            try:
                self.selected = self.history.pop()
                self.darea.queue_draw()
            except IndexError:
                pass
        # TODO: help 'h'/'?' show information about key commands

        return True

    def set_sizes(self, width, height):
        self.width = width
        self.height = height
        self.ibw = 300
        self.ibh = self.height - 10
        self.ibx = self.width - self.ibw - 5
        self.iby = 5
        self.center = (self.width/2, self.height/2)
        self.background = None

    def on_configure_event(self, w, e):
        if e.width != self.width or e.height != self.height:
            self.set_sizes(e.width, e.height)

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

    # Extra information layers
    # information layers provide a scalar value per node, which can be visualized
    # on the chip map
    overlay_info = [
        ('Expression complexity', values)
    ]

    import glob,json
    frames = []
    for fn in glob.glob('perfect6502/flow*.json'):
        try:
            with open(fn,'rb') as f:
                d = json.load(f)
            frames.append(d)
        except ValueError:
            pass
    frames.sort(key=operator.itemgetter('cycle'))

    app = ChipVisualizer(c, overlay_info, frames)
    #app.cur_overlay = 0
    if len(sys.argv)>1:
        app.selected = int(sys.argv[1])
        app.selection_locked = True
    #app.infobox_tab = 1
    Gtk.main()
        
if __name__ == "__main__":    
    main()

