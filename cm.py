import socket
import json
import sys

ADMIN_HOST = '127.0.0.1'
ADMIN_PORT = 5353

def send_command(command):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ADMIN_HOST, ADMIN_PORT))
        s.sendall(command.encode())
        response = s.recv(4096).decode()
        return response

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ['status', 'clear']:
        print("Usage: python admin_client.py [status|clear]")
        sys.exit(1)
    
    command = sys.argv[1]
    response = send_command(command)
    
    if command == 'status':
        try:
            status = json.loads(response)
            if status:
                for key, info in status.items():
                    print(f"Key: {key}")
                    print(f"  Expiration: {info['expiration']}")
                    print(f"  Remaining: {info['remaining_seconds']} seconds")
                    print()
            else:
                print("Cache is empty.")
        except json.JSONDecodeError:
            print("Error decoding status response.")
    else:
        print(response)
