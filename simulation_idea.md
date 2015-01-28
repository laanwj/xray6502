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


