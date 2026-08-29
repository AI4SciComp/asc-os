# Repository boundaries

`asc-os` is the sole generic AI research operating-system repository. It owns
research state, contexts, covers, overlaps, evidence, decisions, lifecycle,
restriction, gluing, CLI, and local stdio MCP.

`asc-cmake` owns CMake build policy. `asc-cpp` and `asc-py` remain
domain-neutral scientific foundations. `asc-devtools` remains a dependency-free
Go developer CLI rather than an agent runtime.

`asc-no` is planned, absent from this implementation, and will own future
neural-operator models, training, evaluation, data, and benchmarks. It must
depend on released public `asc-py` APIs, must not make `asc-py` depend on it,
and must not import ASC OS at runtime.

ASC OS v0.1 contains no C++ and does not modify external scientific repositories.
