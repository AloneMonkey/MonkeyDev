# roothide link stub

`libsubstrate.tbd` is linker metadata from [roothide/lib](https://github.com/roothide/lib/blob/85e9b5b8aff11bbefc59525c64c8f55149926e56/iphone/roothide/libsubstrate.tbd). It contains no executable code and is not copied into the device package. The device supplies the compatible implementation (for example, roothide ElleKit).

The upstream repository documents its text-based link stubs in [LICENSE.md](https://github.com/roothide/lib/blob/85e9b5b8aff11bbefc59525c64c8f55149926e56/LICENSE.md).

## Path API SDK

`include/roothide.h` and `include/module.modulemap` are the unmodified API header and module declaration from [roothide/libroothide](https://github.com/roothide/libroothide/tree/7764c54759009272b4f2f23c18c62b21794fe6dd), under the accompanying MIT `LICENSE`. `libroothide.tbd` is the link declaration from the same pinned [roothide/lib](https://github.com/roothide/lib/blob/85e9b5b8aff11bbefc59525c64c8f55149926e56/iphone/roothide/libroothide.tbd) revision as `libsubstrate.tbd`. No device runtime is redistributed.

Only the roothide scheme exposes `<roothide.h>` and the library search path. The official module declaration supplies automatic linking, without global `-dead_strip_dylibs`: including the header without calling its APIs does not retain a `libroothide` dependency. When used, the implementation is supplied by the device's `roothide` package. Rootless/rootful do not import this SDK or use compatibility stubs. This integration provides path APIs, not automatic rewriting of existing file access or the full vroot SDK.
