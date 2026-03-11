import os
import random
import string
import threading
import time
import subprocess
import sys
import re
import socket
import shutil
from flask import Flask, request, render_template_string

# Configuration
PORT = 5000
AUTHORIZED_KEYS_FILE = os.path.expanduser('~/.ssh/authorized_keys')

def is_debian_based():
    """Check if the system is Debian-based."""
    try:
        # Check for /etc/debian_version or /etc/os-release
        if os.path.exists('/etc/debian_version'):
            return True
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                content = f.read().lower()
                return 'debian' in content or 'ubuntu' in content
        return False
    except Exception:
        return False

def get_ip_addresses():
    ip_addresses = {'private': [], 'public': []}
    try:
        # Create a socket and connect to an external address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # We don't actually connect, just use it to get local IP
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        
        # Categorize the IP
        if any([
            ip.startswith('10.'),
            ip.startswith('172.16.') or any(ip.startswith(f'172.{i}.') for i in range(17, 32)),
            ip.startswith('192.168.')
        ]):
            ip_addresses['private'].append(ip)
        else:
            ip_addresses['public'].append(ip)
    except:
        pass
    return ip_addresses

def validate_ssh_key(key):
    """Validate SSH public key format."""
    # Basic SSH public key format validation
    key = key.strip()
    
    # Common SSH key types
    key_types = ['ssh-rsa', 'ssh-ed25519', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521']
    
    # Check if key starts with a valid type
    if not any(key.startswith(kt) for kt in key_types):
        return False
    
    # Check basic format: type + base64 + comment (optional)
    parts = key.split()
    if len(parts) < 2:
        return False
        
    # Check if the middle part is valid base64
    try:
        base64_part = parts[1]
        # Try to decode base64 - will raise error if invalid
        base64_part.encode('ascii')
        return True
    except:
        return False

# Generate random password
def generate_password():
    """Generate a password consisting of two words separated by a hyphen."""
    words = [
        'red', 'blue', 'green', 'black', 'white', 'gold', 'silver',
        'moon', 'sun', 'star', 'cloud', 'rain', 'wind', 'snow',
        'tree', 'leaf', 'rose', 'pine', 'oak', 'maple', 'bird',
        'fish', 'wolf', 'bear', 'lion', 'tiger', 'eagle', 'hawk',
        'lake', 'river', 'ocean', 'mountain', 'valley', 'forest',
        'swift', 'quick', 'fast', 'calm', 'quiet', 'loud', 'soft'
    ]
    return f"{random.choice(words)}-{random.choice(words)}"

# Flask web app
app = Flask(__name__)
pasted_key = None
password = generate_password()

html_page = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Upload SSH Key</title>
    <link href="https://fonts.googleapis.com/css2?family=PP+Formula&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Creato+Display&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=PP+Formula:wght@400;700&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Creato+Display:wght@400;500;600&display=swap');

        body {
            font-family: 'Creato Display', sans-serif;
            background: linear-gradient(135deg, #010105 0%, #000c14 100%);
            color: white;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px;
            min-height: 100vh;
            margin: 0;
        }
        .container {
            background: rgba(255, 255, 255, 0.05);
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 700px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo {
            max-width: 400px;
            height: auto;
            margin-bottom: 10px;
        }
        h2, h3 {
            font-family: 'PP Formula', sans-serif;
            color: white;
            margin-bottom: 20px;
            text-align: center;
        }
        h2 {
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 10px;
        }
        h3 {
            font-size: 1.8em;
            font-weight: 500;
            margin-bottom: 30px;
        }
        p, label {
            font-size: 16px;
            margin-bottom: 10px;
            color: rgba(255, 255, 255, 0.9);
            line-height: 1.6;
        }
        input[type="password"], textarea {
            width: 100%;
            padding: 12px;
            margin: 10px 0 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            font-size: 14px;
            background: rgba(255, 255, 255, 0.05);
            color: white;
            font-family: 'Creato Display', sans-serif;
        }
        textarea {
            min-height: 120px;
            resize: vertical;
        }
        input[type="submit"], button {
            padding: 14px 24px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            width: 100%;
            font-size: 16px;
            margin-top: 10px;
            font-family: 'PP Formula', sans-serif;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        button {
            background: #000;
            color: white;
            border: 2px solid white;
            position: relative;
        }
        button:hover {
            background: rgba(0, 0, 0, 0.8);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }
        button:disabled {
            background: #2c3e50;
            border-color: rgba(255, 255, 255, 0.3);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
            opacity: 0.7;
        }
        button.loading {
            background: #1a1a1a;
            border-color: rgba(255, 255, 255, 0.5);
        }
        button.loading::after {
            content: '';
            position: absolute;
            width: 20px;
            height: 20px;
            top: 50%;
            left: 50%;
            margin: -10px 0 0 -10px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: button-loading-spinner 0.6s linear infinite;
        }
        @keyframes button-loading-spinner {
            from { transform: rotate(0turn); }
            to { transform: rotate(1turn); }
        }
        input[type="submit"] {
            background: white;
            color: black;
        }
        input[type="submit"]:hover {
            background: rgba(255, 255, 255, 0.9);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }
        .warning {
            color: #D14343;
            font-size: 14px;
            margin-top: 10px;
            padding: 12px;
            background: rgba(209, 67, 67, 0.1);
            border-radius: 8px;
            border: 1px solid rgba(209, 67, 67, 0.3);
        }
        .loading-message {
            display: none;
            color: #3498db;
            font-size: 16px;
            margin: 20px 0;
            padding: 15px;
            background: rgba(52, 152, 219, 0.1);
            border-radius: 8px;
            border: 1px solid rgba(52, 152, 219, 0.3);
            text-align: center;
        }
        .loading-message.visible {
            display: block;
        }
        a {
            color: #3498db;
            text-decoration: none;
            transition: color 0.3s ease;
        }
        a:hover {
            color: #2980b9;
        }
        ::placeholder {
            color: rgba(255, 255, 255, 0.5);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://docs.nunet.io/~gitbook/image?url=https%3A%2F%2F2832281263-files.gitbook.io%2F%7E%2Ffiles%2Fv0%2Fb%2Fgitbook-x-prod.appspot.com%2Fo%2Forganizations%252FHmQiiAfFnBUd24KadDsO%252Fsites%252Fsite_29YoC%252Flogo%252FoWIZXAaXL2h5S8VZIUfb%252Fnunet_logo_update_white%2520%281%29.png%3Falt%3Dmedia%26token%3D21d0f202-a01b-4c7e-9bdb-fda673c338d8&width=260&dpr=4&quality=100&sign=25f98d74&sv=2" alt="NuNet Logo" class="logo">
            <h3>Add SSH public key</h3>
        </div>

        <p>Copy and paste the public key you would like to use to access the NuNet appliance. If you don't already have one you want to use, you can generate a keypair using the button below.</p>
        <p class="warning">⚠️ If you choose to generate a new keypair this takes a bit of processing power and might cause your browser to become unresponsive for 10-20 seconds depending on the power of the machine, it is also likely that your browser may warn about an "unsafe download" or "multiple downloads". This is because they are security keys and they should be traeted carefully.  Click 'Keep' or OK to save your private and public keys. Remember that anyone with the private key can access your appliance so you should keep it very safe, move it from downloads folder and set permissions to keep it secure for more information see <a href="https://docs.nunet.io/docs/developer-documentation/readme/solutions/nunet-appliance/main" target="_blank">Nunet Appliance Documentation</a></p>

        <form method="POST" id="keyForm">
            <button type="button" id="generateButton">Generate SSH Keypair</button>
            
            <div id="loadingMessage" class="loading-message">
                <p>Generating keys... This may take a few seconds. Please wait.</p>
            </div>

            <label>SSH Public Key:</label><br>
            <textarea name="pubkey" rows="10" required placeholder="Paste your SSH public key here..."></textarea><br>

            <label>Password (This is shown on the appliance menu, and required to submit the form):</label><br>
            <input type="password" name="password" required placeholder="Enter the password shown on the appliance menu..."><br>

            <input type="submit" value="Submit Key">
        </form>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/forge/1.3.1/forge.min.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const generateButton = document.getElementById('generateButton');
            
            if (typeof forge !== 'undefined') {
                generateButton.disabled = false;
                generateButton.onclick = generateKeypair;
                console.log('Forge library loaded successfully');
            } else {
                console.error('Forge library not loaded properly');
                generateButton.textContent = 'Key generation not available';
            }
        });

        async function generateKeypair() {
            try {
                const generateButton = document.getElementById('generateButton');
                const originalText = generateButton.textContent;
                
                // Show loading state
                generateButton.textContent = 'Generating keys... Please wait';
                generateButton.disabled = true;
                
                // Generate RSA key pair with 4096 bits
                const keypair = forge.pki.rsa.generateKeyPair({bits: 4096});
                
                // Convert to OpenSSH format
                const publicKey = forge.ssh.publicKeyToOpenSSH(keypair.publicKey, 'generated@nunet');
                const privateKey = forge.ssh.privateKeyToOpenSSH(keypair.privateKey);

                // Update the textarea with the public key
                const textarea = document.querySelector('textarea[name="pubkey"]');
                textarea.value = publicKey;

                // Create and download private key file
                const privateBlob = new Blob([privateKey], { type: 'application/octet-stream' });
                const privateUrl = URL.createObjectURL(privateBlob);
                const aPrivate = document.createElement('a');
                aPrivate.href = privateUrl;
                aPrivate.download = 'nunet_appliance.pem';
                aPrivate.click();
                URL.revokeObjectURL(privateUrl);

                // Create and download public key file
                const publicBlob = new Blob([publicKey + "\n"], { type: 'text/plain' });
                const publicUrl = URL.createObjectURL(publicBlob);
                const aPublic = document.createElement('a');
                aPublic.href = publicUrl;
                aPublic.download = 'nunet_appliance.pub';
                aPublic.click();
                URL.revokeObjectURL(publicUrl);

                // Restore button state
                generateButton.textContent = originalText;
                generateButton.disabled = false;

                alert('Public and private keys downloaded! Please click "Keep" if the browser warns about downloads, and store them safely.');
            } catch (error) {
                console.error('Error generating keypair:', error);
                alert('Error generating keypair. Please try again or use an existing key.');
                
                // Restore button state in case of error
                const generateButton = document.getElementById('generateButton');
                generateButton.textContent = 'Generate SSH Keypair';
                generateButton.disabled = false;
            }
        }
    </script>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def upload_key():
    global pasted_key
    if request.method == 'POST':
        if request.form.get('password') != password:
            return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Error - NuNet Appliance</title>
    <link href="https://fonts.googleapis.com/css2?family=PP+Formula&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Creato+Display&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=PP+Formula:wght@400;700&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Creato+Display:wght@400;500;600&display=swap');

        body {
            font-family: 'Creato Display', sans-serif;
            background: linear-gradient(135deg, #010105 0%, #000c14 100%);
            color: white;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px;
            min-height: 100vh;
            margin: 0;
        }
        .container {
            background: rgba(255, 255, 255, 0.05);
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 700px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            text-align: center;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo {
            max-width: 400px;
            height: auto;
            margin-bottom: 10px;
        }
        h2, h3 {
            font-family: 'PP Formula', sans-serif;
            color: white;
            margin-bottom: 20px;
            text-align: center;
        }
        h2 {
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 10px;
        }
        h3 {
            font-size: 1.8em;
            font-weight: 500;
            margin-bottom: 30px;
            color: #D14343;
        }
        p {
            font-size: 16px;
            margin-bottom: 10px;
            color: rgba(255, 255, 255, 0.9);
            line-height: 1.6;
        }
        .error-icon {
            font-size: 48px;
            color: #D14343;
            margin-bottom: 20px;
        }
        .back-button {
            display: inline-block;
            background: #000;
            color: white;
            border: 2px solid white;
            padding: 14px 24px;
            border-radius: 8px;
            font-family: 'PP Formula', sans-serif;
            font-size: 16px;
            font-weight: 500;
            text-decoration: none;
            margin-top: 20px;
            transition: all 0.3s ease;
        }
        .back-button:hover {
            background: rgba(255, 255, 255, 0.1);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://docs.nunet.io/~gitbook/image?url=https%3A%2F%2F2832281263-files.gitbook.io%2F%7E%2Ffiles%2Fv0%2Fb%2Fgitbook-x-prod.appspot.com%2Fo%2Forganizations%252FHmQiiAfFnBUd24KadDsO%252Fsites%252Fsite_29YoC%252Flogo%252FoWIZXAaXL2h5S8VZIUfb%252Fnunet_logo_update_white%2520%281%29.png%3Falt%3Dmedia%26token%3D21d0f202-a01b-4c7e-9bdb-fda673c338d8&width=260&dpr=4&quality=100&sign=25f98d74&sv=2" alt="NuNet Logo" class="logo">
            <h3>Invalid Password</h3>
        </div>
        <div class="error-icon">⚠️</div>
        <p>The password you entered does not match the one shown on the appliance menu.</p>
        <p>Please check the password and try again.</p>
        <a href="/" class="back-button">Go Back</a>
    </div>
</body>
</html>
''', 403
            
        submitted_key = request.form.get('pubkey', '').strip()
        if not submitted_key:
            return "<h3>Error: No SSH key provided!</h3>", 400
            
        if not validate_ssh_key(submitted_key):
            return "<h3>Error: Invalid SSH key format!</h3>", 400
            
        pasted_key = submitted_key
        return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Key Received - NuNet Appliance</title>
    <link href="https://fonts.googleapis.com/css2?family=PP+Formula&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Creato+Display&display=swap" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=PP+Formula:wght@400;700&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Creato+Display:wght@400;500;600&display=swap');

        body {
            font-family: 'Creato Display', sans-serif;
            background: linear-gradient(135deg, #010105 0%, #000c14 100%);
            color: white;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px;
            min-height: 100vh;
            margin: 0;
        }
        .container {
            background: rgba(255, 255, 255, 0.05);
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 700px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            text-align: center;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo {
            max-width: 400px;
            height: auto;
            margin-bottom: 10px;
        }
        h2, h3 {
            font-family: 'PP Formula', sans-serif;
            color: white;
            margin-bottom: 20px;
            text-align: center;
        }
        h2 {
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 10px;
        }
        h3 {
            font-size: 1.8em;
            font-weight: 500;
            margin-bottom: 30px;
        }
        p {
            font-size: 16px;
            margin-bottom: 10px;
            color: rgba(255, 255, 255, 0.9);
            line-height: 1.6;
        }
        .success-icon {
            font-size: 48px;
            color: #27ae60;
            margin-bottom: 20px;
        }
        .footer {
            color: rgba(255, 255, 255, 0.5);
            margin-top: 30px;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://docs.nunet.io/~gitbook/image?url=https%3A%2F%2F2832281263-files.gitbook.io%2F%7E%2Ffiles%2Fv0%2Fb%2Fgitbook-x-prod.appspot.com%2Fo%2Forganizations%252FHmQiiAfFnBUd24KadDsO%252Fsites%252Fsite_29YoC%252Flogo%252FoWIZXAaXL2h5S8VZIUfb%252Fnunet_logo_update_white%2520%281%29.png%3Falt%3Dmedia%26token%3D21d0f202-a01b-4c7e-9bdb-fda673c338d8&width=260&dpr=4&quality=100&sign=25f98d74&sv=2" alt="NuNet Logo" class="logo">
            <h3>Key Successfully Received</h3>
        </div>
        <div class="success-icon">✓</div>
        <p>Your SSH public key has been submitted and is now pending confirmation.</p>
        <p>Please return to your appliance menu and confirm the addition of this key.</p>
        <p class="footer">You can now close this window.</p>
    </div>
</body>
</html>
'''
    return render_template_string(html_page)

def run_server():
    try:
        app.run(host='0.0.0.0', port=PORT)
    except Exception as e:
        print(f"Error starting server: {e}")
        os._exit(1)

def main():
    global pasted_key
    
    # Check if running on Debian-based system
    if not is_debian_based():
        print("Error: This script is only supported on Debian-based systems.")
        print("Please run this script on a Debian or Ubuntu system.")
        sys.exit(1)
    
    
    # Check if authorized_keys directory exists and is writable
    ssh_dir = os.path.dirname(AUTHORIZED_KEYS_FILE)
    if not os.path.exists(ssh_dir):
        try:
            os.makedirs(ssh_dir, mode=0o700)
        except Exception as e:
            print(f"Error creating SSH directory: {e}")
            return

    ip_addresses = get_ip_addresses()

    # Clear the screen
    os.system('clear' if os.name == 'posix' else 'cls')
    
    print("\n" + "="*80)
    print("                         NuNet Appliance SSH Key Setup")
    print("="*80 + "\n")

    # Show warning if public IPs are detected
    if ip_addresses['public']:
        print("⚠️  WARNING: Public IP Address Detected!")
        print("-"*80)
        print("Your appliance appears to be accessible from the internet. This is potentially unsafe.")
        print("If you already have SSH access, you should:")
        print("1. Access the appliance via SSH")
        print("2. Add your public key directly to ~/.ssh/authorized_keys")
        print("\nDo you want to continue with the web-based public key submission anyway? (y/n): ")
        if input().strip().lower() != 'y':
            print("\nSetup cancelled. Please add your SSH key manually.")
            sys.exit(0)
        print("\n" + "="*80 + "\n")
    
    print("INSTRUCTIONS:")
    print("-"*80)
    print("1. On the computer you want to use to connect to the appliance,") 
    print("   open a web browser and navigate to one of these addresses:")
    
    # Show private IPs first
    if ip_addresses['private']:
        for ip in ip_addresses['private']:
            print(f"   \033[92mhttp://{ip}:{PORT}\033[0m")
    
    # Show public IPs with warning
    if ip_addresses['public']:
        print("\n   Alternative public addresses (use only if local addresses don't work):")
        for ip in ip_addresses['public']:
            print(f"   \033[91mhttp://{ip}:{PORT}\033[0m")
        print("\n   ⚠️  Warning: Using public IPs may expose the setup page to the internet!")
    
    print("\n2. In order to submit your public key, you will need to enter this password:")
    print(f"   \033[92m{password}\033[0m")
    print("\n3. Follow the instructions on the webpage to add your SSH key")
    print("-"*80 + "\n")
    
    print("The web server is now running and waiting for your SSH key...")
    print("(Press Ctrl+C to cancel at any time)\n")

    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    try:
        print("\nWaiting for SSH key submission...")
        while pasted_key is None:
            time.sleep(1)
            
        print("\nSSH Public Key received successfully!")
        print("-"*80)
        print("Received key:")
        print(pasted_key)
        print("-"*80)

        while True:
            choice = input("\nDo you want to add this key to your authorized_keys file? (y/n): ").strip().lower()
            if choice in ['y', 'n']:
                break
            print("Please enter 'y' for yes or 'n' for no.")

        if choice == 'y':
            try:
                os.chmod(ssh_dir, 0o700)
                
                if not os.path.exists(AUTHORIZED_KEYS_FILE):
                    with open(AUTHORIZED_KEYS_FILE, 'w') as f:
                        pass
                    os.chmod(AUTHORIZED_KEYS_FILE, 0o600)
                
                with open(AUTHORIZED_KEYS_FILE, 'a') as f:
                    f.write(pasted_key.strip() + '\n')
                print("\n✓ Key successfully added to authorized_keys file")
                print("✓ You can now use this key to SSH into your appliance")
            except Exception as e:
                print(f"\nError adding key: {e}")
        else:
            print("\nKey was not added.")

    except KeyboardInterrupt:
        print("\nSetup cancelled by user.")
        sys.exit(0)
    finally:
        print("\nClosing web server...")
        sys.exit(0)

if __name__ == '__main__':
    main()
