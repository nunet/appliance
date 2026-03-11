import subprocess
import sys
import os

print("Wrapper script started")

def install_dependencies():
    print("Installing required packages...")
    try:
        subprocess.check_call([
            "sudo", "apt-get", "update"
        ])
        subprocess.check_call([
            "sudo", "apt-get", "install", "-y",
            "python3-flask", "python3-netifaces", "openssh-server"
        ])
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)

def run_main_script():
    script_path = os.path.join(os.path.dirname(__file__), "configure-ssh-access.py")
    try:
        subprocess.check_call(["python3", script_path])
    except subprocess.CalledProcessError as e:
        print(f"Failed to run main script: {e}")
        sys.exit(1)

def main():
    install_dependencies()
    run_main_script()

if __name__ == "__main__":
    main()