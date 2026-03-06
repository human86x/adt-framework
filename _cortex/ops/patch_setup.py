
path = 'setup.py'
with open(path, 'r') as f:
    content = f.read()
new_content = content.replace('version="0.1.0"', 'version="0.3.3"')
with open(path, 'w') as f:
    f.write(new_content)
print('setup.py updated.')