import json
import os

tasks_path = "_cortex/tasks.json"
with open(tasks_path, "r") as f:
    data = json.load(f)

specs_to_approve = ["SPEC-017", "SPEC-033", "SPEC-038", "SPEC-039", "SPEC-042", "SPEC-014", "SPEC-015", "SPEC-018", "SPEC-020", "SPEC-021", "SPEC-027", "SPEC-031", "SPEC-032", "SPEC-034", "SPEC-035", "SPEC-036", "SPEC-037"]
count = 0

for task in data.get("tasks", []):
    if task.get("status") == "completed" and task.get("review_status") == "pending":
        if task.get("spec_ref") in specs_to_approve:
            task["review_status"] = "approved"
            task["last_updated_by"] = "GEMINI (Systems_Architect)"
            # print(f"Approving {task.get(\"id\")} ({task.get(\"spec_ref\")})")
            count += 1

print(f"Approved {count} tasks.")
with open(tasks_path + ".new", "w") as f:
    json.dump(data, f, indent=2)
