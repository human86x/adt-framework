
import os
import subprocess

def resolve_user_path():
    shell = os.environ.get("SHELL", "/bin/bash")
    try:
        output = subprocess.check_output([shell, "-l", "-c", "echo $PATH"], text=True).strip()
        if output:
            return output
    except:
        pass
    
    current = os.environ.get("PATH", "")
    home = os.environ.get("HOME", "/root")
    return f"{home}/.npm-global/bin:{home}/.cargo/bin:{home}/.local/bin:{current}"

def resolve_command(command, user_path):
    if command.startswith('/'):
        return command
    for directory in user_path.split(':'):
        # Handle ~ in PATH (common in some shell setups)
        if directory.startswith('~'):
            directory = os.path.expanduser(directory)
        candidate = os.path.join(directory, command)
        if os.path.exists(candidate):
            return candidate
    return command

user_path = resolve_user_path()
print(f"USER_PATH: {user_path}")
print(f"gemini -> {resolve_command('gemini', user_path)}")
print(f"claude -> {resolve_command('claude', user_path)}")
