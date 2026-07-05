"""Enhanced parameter decoding for nested types."""
from eth_abi import decode_single
import re

def decode_parameter(type_str: str, data: bytes):
    """Decode a single parameter, handling nested arrays and structs."""
    # Handle nested arrays
    if "[]" in type_str:
        base_type = type_str.replace("[]", "")
        array = decode_single(f"{type_str}", data)
        return [decode_parameter(base_type, item) if isinstance(item, bytes) else item for item in array]
    # Handle tuples/structs
    if "(" in type_str:
        return decode_single(type_str, data)
    # Simple types
    return decode_single(type_str, data)

def decode_parameters(types: list, data: bytes) -> list:
    """Decode multiple parameters."""
    from eth_abi import decode_abi
    return list(decode_abi(types, data))
