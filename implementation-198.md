# Implementation for #198

See issue #198 for details.

The `decodeParameter` in `sdk/src/utils/encoding.ts` only handles fixed-size types (uint256, address, bool). Dynamic types (string, bytes, arrays) are returned as raw hex.

### Fix

- Add string decoding: read offset, then length, then UTF-8 data
- Add bytes decoding: read offset, length, raw data
- Add dynamic array decoding: read offset, length, then elements
- Document your changes by adding the standard `@fix-author` block to the top of the modified file. Include: name, date, and the complet