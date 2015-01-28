Interesting ideas

How to speed up the perfect6502 sim further?

- Compile design to CPU code.
  Instead of general-purpose emulating code, generate CPU code
  that emulates the design. Compilation versus interpretation.
  
  For
  - pure logic gates 
  - simple flipflops and memory elements
  
  This is straightforward.
  There will be transistor groups to which this is not applicatble and 
  need transistor-level simulation.

- Consider paralellism - CPUs are massively parallel at a bit level, and can do
  32/64 logical ops at the cost of one.

  However 'routing' is expensive. Most general purpose CPU architectures
  don't have instructions to permute and swizzle bits in arbitrary patterns,
  which means substantial logic would be generated for extracting and inserting
  individual bits.

  After extracting gates, it is possible to 'route' the resulting logic
  to an achitecture that is efficiently executable on CPU.

  For the 6502 I don't expect much more than 8-bit parallelism, but it's
  something.

