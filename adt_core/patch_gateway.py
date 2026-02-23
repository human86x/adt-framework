import subprocess
import os
import sys

def main():
    with open("adt_core/dttp/gateway.py", "r") as f:
        content = f.read()

    old_snippet = """    def __init__(self, 
                 policy_engine: PolicyEngine, 
                 action_handler: ActionHandler, 
                 logger: ADSLogger):
        self.policy_engine = policy_engine
        self.action_handler = action_handler
        self.logger = logger"""

    new_snippet = """    def __init__(self, 
                 policy_engine: PolicyEngine, 
                 action_handler: ActionHandler, 
                 logger: ADSLogger,
                 is_framework: bool = False):
        self.policy_engine = policy_engine
        self.action_handler = action_handler
        self.logger = logger
        self.is_framework = is_framework"""

    if old_snippet not in content:
        print("Error: old_snippet not found in content")
        sys.exit(1)
        
    updated_content = content.replace(old_snippet, new_snippet)
    
    # 2nd replacement
    old_snippet2 = """        # 1. Sovereign Path Check (Tier 1) - SPEC-020 Section 2.1
        if normalized_path in SOVEREIGN_PATHS:"""
    new_snippet2 = """        # 1. Sovereign Path Check (Tier 1) - SPEC-020 Section 2.1
        # Skip for external projects (SPEC-031)
        if self.is_framework and normalized_path in SOVEREIGN_PATHS:"""
        
    if old_snippet2 not in updated_content:
        print("Error: old_snippet2 not found in content")
        sys.exit(1)
        
    updated_content = updated_content.replace(old_snippet2, new_snippet2)
    
    # 3rd replacement
    old_snippet3 = """        if normalized_path in CONSTITUTIONAL_PATHS:
            is_tier2 = True
            tier2_reason = f"Tier 2 path {normalized_path}\""""
    new_snippet3 = """        if self.is_framework and normalized_path in CONSTITUTIONAL_PATHS:
            is_tier2 = True
            tier2_reason = f"Tier 2 path {normalized_path}\""""
            
    if old_snippet3 not in updated_content:
        print("Error: old_snippet3 not found in content")
        sys.exit(1)
        
    updated_content = updated_content.replace(old_snippet3, new_snippet3)

    # Submit via DTTP
    cmd = [
        "python3", "adt_sdk/hooks/dttp_request.py",
        "--action", "edit",
        "--file", "adt_core/dttp/gateway.py",
        "--spec", "SPEC-017",
        "--rationale", "Implementing SPEC-031 Phase B multi-project isolation in DTTPGateway.",
        "--justification", "External Project Governance (SPEC-031) requires conditional sovereign path checks.",
        "--content", updated_content,
        "--role", "Backend_Engineer"
    ]
    
    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
