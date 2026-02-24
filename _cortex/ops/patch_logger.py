from adt_sdk.client import ADTClient
import os

client = ADTClient(dttp_url="http://localhost:5002", agent_name="GEMINI", role="Backend_Engineer")

old_string = """            except (json.JSONDecodeError, OSError):
                return None"""

new_string = """            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error reading last event from {self.file_path}: {e}")
                return None"""

try:
    response = client.request(
        spec_id="SPEC-017",
        action="patch",
        params={
            "file": "adt_core/ads/logger.py",
            "old_string": old_string,
            "new_string": new_string,
            "tier2_justification": "Modifying Constitutional path to implement mandatory robustness fix from SPEC-018 Section 3.6."
        },
        rationale="Fix silent except block as per SPEC-018 Section 3.6"
    )
    print(response)
except Exception as e:
    print(f"Error: {e}")
