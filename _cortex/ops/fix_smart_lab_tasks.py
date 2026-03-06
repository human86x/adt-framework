import json
path = '/home/human/Projects/smart-lab/_cortex/tasks.json'
with open(path, 'r') as f:
    data = json.load(f)
for task in data.get('tasks', []):
    if 'role' in task and 'assigned_to' not in task:
        task['assigned_to'] = task.pop('role')
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
print('Fixed smart-lab tasks.json')