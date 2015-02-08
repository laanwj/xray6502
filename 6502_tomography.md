Data flow tracking on the virtual 6502
CPU tomography
Wladimir van der Laan

This kind of data flow analysis in software is quite popular these days
See e.g.: https://www.cs.ucsb.edu/~sherwood/pubs/TACO-12-tomo.pdf
ACM Transactions on Architecture and Code Optimization, Vol. 9, No. 1, Article 3, Publication date: March 2012

"Is it possible to do data flow tracking on a per-transistor level and
get sensible results on an instruction level?"

Propagate tags over transistors
--------------------------------

Multiple bits can be followed using different colors.

Tag propagation is the tricky issue. That the tag has to propagate from c1 to c2
of an open transistor is straightforward, but what to do when the gate value
of a transistor is tagged is a more complicated.

Adopted the rule that what contributes to the output (e.g., further transistor
gates), affects the tag of the output.

What contributes to the output? Transistors that cannot be switched
without affecting the output value (e.g. are critical to it).

So for every node, compare new value for transistors at current value,
and tagged transistors with toggled value. If these are different
the tagged transistors still contribute to the value, thus the value
should be propagated.

6502 info: flag bits
----------------------

    7 6 5 4 3 2 1 0
    N V 1 B D I Z C

p7 | N | Negative flag
p6 | V | Overflow flag
p5 | 1 | Unused flag
p4 | B | Break flag
p3 | D | Decimal flag
p2 | I | Interrupt disable flag
p1 | Z | Zero flag
p0 | C | Carry flag

