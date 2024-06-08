import network
import socket
import select
from machine import Pin, reset
import time

# Set up the relay pins
relay_open = Pin(26, Pin.OUT)
relay_close = Pin(27, Pin.OUT)
relay_open.off()
relay_close.off()

# Set up the onboard LED pin (usually GPIO 2 on ESP32 boards)
led = Pin(2, Pin.OUT)
led.off()  # Turn off the LED initially

# Configure the ESP32 as an Access Point
ssid = 'Sam_Rc'
password = '12345678'

# Function to activate the Access Point
def activate_access_point():
    print('Activating Access Point...')
    ap = network.WLAN(network.AP_IF)  # Initialize the WLAN interface in AP mode
    ap.config(essid=ssid, password=password, authmode=network.AUTH_WPA_WPA2_PSK)  # Set WPA2 security
    ap.active(True)  # Activate the AP mode

    while not ap.active():
        pass  # Wait until the AP mode is active

    print('Access Point Active')
    print('AP Config:', ap.ifconfig())  # Print the network configuration
    ip_address = ap.ifconfig()[0]
    return ap, ip_address

# Define the HTML for the web interface
html = """<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Relay Control</title>
    <style>
        body { background-color: gray; color: white; text-align: center; font-family: Arial, sans-serif; }
        h1 { font-size: 3em; font-weight: bold; margin-top: 20px; }
        h2 { font-size: 2em; margin-top: 20px; }
        button { font-size: 2em; margin: 20px; padding: 10px 20px; }
    </style>
</head>
<body>
    <h1>Sam's RC</h1>
    <h2>Relays Control</h2>
    <button onclick="openStore()">Relay 1</button>
    <button onclick="closeStore()">Relay 2</button>
    <button onclick="exitPage()">Exit</button>
    <script>
        function openStore() {
            fetch('/open');
        }
        function closeStore() {
            fetch('/close');
        }
        function exitPage() {
            fetch('/exit');
        }
    </script>
</body>
</html>
"""

# Define the HTML for the logout page
logout_html = """<!DOCTYPE html>
<html>
<head>
    <title>Logging out</title>
    <style>
        body { background-color: gray; color: white; text-align: center; font-family: Arial, sans-serif; }
        h1 { font-size: 3em; margin-top: 20px; }
        p { font-size: 1.5em; }
    </style>
</head>
<body>
    <h1>Logging out</h1>
    <p>Go to WiFi to log in again</p>
</body>
</html>
"""

# Helper function to convert IP address string to bytes
def ip_to_bytes(ip):
    return bytes(map(int, ip.split('.')))

# Function to handle DNS queries
def handle_dns_request(data, addr, dns, ip_address):
    # Build a DNS response packet
    response = data[:2] + b'\x81\x80'  # Response flags
    response += data[4:6] + data[4:6] + b'\x00\x00\x00\x00'  # Questions and Answers count
    response += data[12:]  # Original question
    response += b'\xc0\x0c'  # Pointer to the domain name in the question
    response += b'\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04'  # Response type and TTL
    response += ip_to_bytes(ip_address)  # Respond with ESP32's IP address

    # Send the response
    dns.sendto(response, addr)

# Main function to set up the server and DNS
def start_server():
    server_running = True
    while server_running:
        ap, ip_address = activate_access_point()

        # Set up the web server
        addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow address reuse
        s.bind(addr)
        s.listen(1)

        print('Listening on', addr)

        # Set up a simple DNS server
        dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dns.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow address reuse
        dns.bind(('0.0.0.0', 53))

        while True:
            # Use select to wait for incoming connections or DNS queries
            r, _, _ = select.select([s, dns], [], [])
            for ready_socket in r:
                if ready_socket == s:
                    # Handle HTTP request
                    cl, addr = s.accept()
                    print('Client connected from', addr)
                    led.on()  # Turn on the LED when a client connects
                    try:
                        request = cl.recv(1024)
                        request_str = request.decode()
                        print("Request:", request_str)

                        if 'GET /open' in request_str:
                            relay_close.off()  # Ensure the close relay is off
                            relay_open.on()    # Turn on the open relay
                        elif 'GET /close' in request_str:
                            relay_open.off()   # Ensure the open relay is off
                            relay_close.on()   # Turn on the close relay
                        elif 'GET /exit' in request_str:
                            # Serve the logout page
                            cl.send('HTTP/1.1 200 OK\n')
                            cl.send('Content-Type: text/html\n')
                            cl.send('Connection: close\n\n')
                            cl.sendall(b"<html><body><h1>Logging out</h1></body></html>")
                            cl.close()
                            # Give some time for the client to receive the response
                            time.sleep(1)
                            # Cleanly close the server sockets
                            s.close()
                            dns.close()
                            # Break the inner while loop to restart the server
                            server_running = False
                            break

                        # Serve the control page
                        else:
                            cl.send('HTTP/1.1 200 OK\n')
                            cl.send('Content-Type: text/html\n')
                            cl.send('Connection: close\n\n')
                            cl.sendall(html)
                    finally:
                        cl.close()
                        led.off()  # Turn off the LED when the client disconnects

                elif ready_socket == dns:
                    # Handle DNS request
                    data, addr = dns.recvfrom(512)
                    handle_dns_request(data, addr, dns, ip_address)

            if not server_running:
                break

        # Delay to ensure the network stack releases the address
        time.sleep(1)
        if not server_running:
            server_running = True

# Start the server for the first time
start_server()
