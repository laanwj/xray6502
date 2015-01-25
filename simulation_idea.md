Hierarchical simulation of NMOS transistors
============================================

A transistor has three nodes: gate, c1, c2. gate is an input, c1 and c2 can be input as well as output.
It is simulated as a switch that connects c1 and c2 if gate is 1.

The current value of a node (wire) depends on what it is connected to, with what drive strength.
The following numbered states are distinguished:

    lo = 0x00
    hi = 0x01
    pullup = 0x03
    pulldown = 0x04
    vcc = 0x05
    vss = 0x06

When two nodes are connected (e.g. when a transistor is open), the highest node state wins. For example
if the node is connected to VSS through some path, the state that wins will be `contains_vss`.

Observation: it is always possible to connect two nodes later and determine the common state by just
  excuting a min() operator.

Collect groups hierarchically in parallel
------------------------------------------

'Segmentation' approach - find subgraphs.

Each stage merges groups from last stage.

Start with groups with one per node.

'Running' a transistor will merge two groups if the gate is high.
However: this is not a tree: cycles exist so it is possible that the groups are already combined
         via another path. In this case the merging will be a no-op.

Produces C(g1,g2) records - where g1 and g2 refer to group IDs from the last stage
   no further merging makes sense on the outputs.

   Any further transistor referring to nodes in g1 and g2 will refer to C(g1,g2) instead.

At the end we'll have found all groups, as well as values for all groups.
Propagate these values into the nodes, and run another run of the algorithm.

Run parts of circuit in parallel
---------------------------------

This makes it possible to run every transistor in parallel.
Based on splitting then recombining.
Can be done in the 2D graph of the circuit, but also virtually.

The wires are 'cut' so that every transistor X gets dedicated nodes:

  `tX_gate`
  `tX_c1`
  `tX_c2`

Initially, nodes get assigned 

  - vcc/vss if the node is connected to VCC or VSS directly
  - pullup/pulldown if the node is a pullup or pulldown node
  - lo/hi state based on results of the last simulation step

In succesive hierarchical stages these nodes are combined by processing elements
Based on connectivity.
Either real transistors, or 'fake' always open transistors that just connect two virtual nodes.

eg t0 connects `t0_c1` and `t0_c2`

eg t0_c1 connects to node n1
   t1_c2 connects to node n1

state(`l2_t0_c1_t1_c2`) = min(t0_c1, t0_c2)

To combine blocks:

  find out which connections connect block A and B
  merge these nodes
  keep track of which nodes are merged


