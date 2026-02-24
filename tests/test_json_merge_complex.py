import json
import os
import unittest

def deep_merge(base, update):
    for key, value in update.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base

class TestJsonMergeComplex(unittest.TestCase):
    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}
        expected = {"a": 1, "b": 3, "c": 4}
        self.assertEqual(deep_merge(base, update), expected)

    def test_deep_nesting(self):
        base = {"a": {"b": {"c": 1}}}
        update = {"a": {"b": {"d": 2}}}
        expected = {"a": {"b": {"c": 1, "d": 2}}}
        self.assertEqual(deep_merge(base, update), expected)

    def test_overwrite_type_mismatch_dict_to_val(self):
        base = {"a": {"b": 1}}
        update = {"a": 2}
        expected = {"a": 2}
        self.assertEqual(deep_merge(base, update), expected)

    def test_overwrite_type_mismatch_val_to_dict(self):
        base = {"a": 1}
        update = {"a": {"b": 2}}
        expected = {"a": {"b": 2}}
        self.assertEqual(deep_merge(base, update), expected)

    def test_new_deep_branch(self):
        base = {"a": 1}
        update = {"b": {"c": {"d": 3}}}
        expected = {"a": 1, "b": {"c": {"d": 3}}}
        self.assertEqual(deep_merge(base, update), expected)

    def test_list_replacement(self):
        # Current logic replaces lists, doesn't merge them.
        base = {"a": [1, 2]}
        update = {"a": [3, 4]}
        expected = {"a": [3, 4]}
        self.assertEqual(deep_merge(base, update), expected)

    def test_complex_specs_scenario(self):
        # Simulating adding a role to an existing spec and adding a new spec
        base = {
            "specs": {
                "SPEC-001": {
                    "title": "First Spec",
                    "roles": ["Architect"]
                }
            }
        }
        update = {
            "specs": {
                "SPEC-001": {
                    "roles": ["Architect", "Developer"]
                },
                "SPEC-002": {
                    "title": "Second Spec",
                    "roles": ["Developer"]
                }
            }
        }
        # Note: SPEC-001 title should be preserved if not in update
        # WAIT: In my current implementation, if I provide SPEC-001: {"roles": [...]},
        # it will overwrite the WHOLE SPEC-001 object unless I nest the update.
        # Let's check.
        result = deep_merge(base, update)
        
        # If I want to preserve title, update should be:
        # {"specs": {"SPEC-001": {"roles": [...]}}}
        # Since update HAS {"specs": {"SPEC-001": {...}}}, deep_merge will recurse into "specs"
        # and then into "SPEC-001".
        
        self.assertEqual(result["specs"]["SPEC-001"]["title"], "First Spec")
        self.assertEqual(result["specs"]["SPEC-001"]["roles"], ["Architect", "Developer"])
        self.assertEqual(result["specs"]["SPEC-002"]["title"], "Second Spec")

if __name__ == "__main__":
    unittest.main()
