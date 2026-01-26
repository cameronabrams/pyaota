"""Serialization utilities for LayoutConfig with Pint quantities."""

import json
from dataclasses import asdict, fields
from typing import Any, Dict
import pint

def serialize_quantity(q: pint.Quantity) -> Dict[str, Any]:
    """Convert a Pint Quantity to a serializable dict."""
    return {
        "magnitude": float(q.magnitude),
        "units": str(q.units)
    }

def deserialize_quantity(data: Dict[str, Any], ureg: pint.UnitRegistry) -> pint.Quantity:
    """Reconstruct a Pint Quantity from a dict."""
    return data["magnitude"] * ureg(data["units"])

def serialize_layout_config(config, ureg: pint.UnitRegistry) -> Dict[str, Any]:
    """
    Serialize LayoutConfig to a JSON-compatible dict.
    
    Args:
        config: LayoutConfig instance
        ureg: The UnitRegistry used by the config
        
    Returns:
        Dict that can be JSON serialized
    """
    result = {}
    
    for field in fields(config):
        value = getattr(config, field.name)
        
        if isinstance(value, pint.Quantity):
            # Single quantity
            result[field.name] = serialize_quantity(value)
            
        elif isinstance(value, tuple):
            # Check if tuple contains Quantities
            if value and isinstance(value[0], pint.Quantity):
                result[field.name] = [serialize_quantity(q) for q in value]
            else:
                result[field.name] = list(value)
                
        elif isinstance(value, (list, tuple)):
            # Handle sequences
            result[field.name] = list(value)
            
        else:
            # Plain value (int, float, str, etc.)
            result[field.name] = value
    
    return result

def deserialize_layout_config(data: Dict[str, Any], config_class, ureg: pint.UnitRegistry):
    """
    Deserialize a dict to LayoutConfig.
    
    Args:
        data: Dict from serialize_layout_config or JSON
        config_class: The LayoutConfig class
        ureg: The UnitRegistry to use for quantities
        
    Returns:
        LayoutConfig instance
    """
    kwargs = {}
    
    for field in fields(config_class):
        if field.name not in data:
            # Use default if available
            continue
            
        value = data[field.name]
        
        # Check field type annotation to determine how to deserialize
        field_type = str(field.type)
        
        if isinstance(value, dict) and "magnitude" in value and "units" in value:
            # Single Quantity
            kwargs[field.name] = deserialize_quantity(value, ureg)
            
        elif isinstance(value, list) and value and isinstance(value[0], dict) and "magnitude" in value[0]:
            # Tuple/list of Quantities
            kwargs[field.name] = tuple(deserialize_quantity(q, ureg) for q in value)
            
        elif isinstance(value, list) and "Tuple" in field_type:
            # Plain tuple
            kwargs[field.name] = tuple(value)
            
        elif isinstance(value, list) and "Sequence" in field_type:
            # Sequence (keep as tuple for immutability)
            kwargs[field.name] = tuple(value)
            
        else:
            # Plain value
            kwargs[field.name] = value
    
    return config_class(**kwargs)

def save_layout_config(config, filepath: str, ureg: pint.UnitRegistry):
    """Save LayoutConfig to JSON file."""
    data = serialize_layout_config(config, ureg)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def load_layout_config(filepath: str, config_class, ureg: pint.UnitRegistry):
    """Load LayoutConfig from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return deserialize_layout_config(data, config_class, ureg)


# Example usage:
if __name__ == "__main__":
    from dataclasses import dataclass
    from typing import Tuple, Sequence
    
    ureg = pint.UnitRegistry()
    
    @dataclass
    class TestConfig:
        num_questions: int
        bubble_radius: pint.Quantity = 24 * ureg.pxl
        page_margins: Tuple[pint.Quantity, pint.Quantity] = (1.0 * ureg.inch, 1.0 * ureg.inch)
        choice_keys: Sequence[str] = ("a", "b", "c", "d")
    
    # Create instance
    config = TestConfig(
        num_questions=50,
        bubble_radius=30 * ureg.pxl,
        page_margins=(1.5 * ureg.inch, 2.0 * ureg.inch)
    )
    
    # Serialize
    serialized = serialize_layout_config(config, ureg)
    print("Serialized:")
    print(json.dumps(serialized, indent=2))
    
    # Deserialize
    restored = deserialize_layout_config(serialized, TestConfig, ureg)
    print("\nRestored:")
    print(f"num_questions: {restored.num_questions}")
    print(f"bubble_radius: {restored.bubble_radius}")
    print(f"page_margins: {restored.page_margins}")
    print(f"choice_keys: {restored.choice_keys}")
    
    # Save/load from file
    save_layout_config(config, "test_config.json", ureg)
    loaded = load_layout_config("test_config.json", TestConfig, ureg)
    print("\nLoaded from file:")
    print(f"bubble_radius: {loaded.bubble_radius}")
