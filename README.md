
# DNS Reverse Proxy

A lightweight DNS proxy daemon that forwards DNS queries to multiple upstream servers in parallel, returning the response from the highest-priority server that provides a successful resolution. Includes caching for successful responses and an admin interface to manage the cache.

## Features
- Queries multiple upstream DNS servers simultaneously, selecting the response from the highest-priority server (lowest priority number).
- Immediate response if the highest-priority server (priority 1) provides a successful answer.
- Caches successful resolutions (NOERROR with answers) based on the minimum TTL of the response.
- Admin interface to view cache status or clear the cache without stopping the daemon.
- Supports debug logging for detailed query and response information.
- Configurable via `/etc/dns.config` with support for comments.

## Requirements
- Python 3.6+
- `dnspython` library (`pip install dnspython`)

## Installation
1. **Clone the Repository**:
   ```bash
   git clone <your-repo-url>
   cd <your-repo-name>
   ```

2. **Install Dependencies**:
   ```bash
   pip install dnspython
   ```

3. **Set Up Configuration**:
   - Create or edit `/etc/dns.config` with your upstream DNS servers and their priorities.
   - Example `/etc/dns.config`:
     ```plaintext
     # Primary local DNS server
     192.168.1.27 1
     // Secondary local server
     192.168.1.28 2
     # Google DNS
     8.8.8.8 3
     // Google secondary
     8.8.4.4 4
     ```
   - Format: `<IP> <priority>` (lower priority number = higher priority).
   - Comments (`#` or `//`) and empty lines are ignored.

4. **Run the Daemon**:
   - Run as root (required for binding to port 53):
     ```bash
     sudo python3 dns-rproxy.py
     ```
   - For debug logging, add the `--debug` flag:
     ```bash
     sudo python3 dns-rproxy.py --debug
     ```

5. **Optional: Set Up as a Systemd Service**:
   - Create `/etc/systemd/system/dns-rproxy.service`:
     ```ini
     [Unit]
     Description=DNS Reverse Proxy Daemon
     After=network.target

     [Service]
     ExecStart=/usr/bin/python3 /path/to/dns-rproxy.py --debug
     Restart=always

     [Install]
     WantedBy=multi-user.target
     ```
   - Enable and start:
     ```bash
     sudo systemctl enable dns-rproxy
     sudo systemctl start dns-rproxy
     ```

## Usage
- **DNS Queries**:
  - Configure clients to use the machine's IP as their DNS server.
  - Test with:
    ```bash
    dig @<machine_ip> example.com
    ```
  - The daemon queries all upstream servers in parallel, returning the response from the highest-priority server with a successful resolution (NOERROR with answers). If the priority 1 server responds successfully, it returns immediately.

- **Cache Management**:
  - Use `cm.py` to interact with the daemon's admin interface (runs on `127.0.0.1:5353`).
  - View cache status:
    ```bash
    python3 cm.py status
    ```
    Output example:
    ```
    Key: ('example.com.', 1, 1)
      Expiration: Thu Sep 04 16:30:00 2025
      Remaining: 3470 seconds
    ```
  - Clear cache:
    ```bash
    python3 cm.py clear
    ```
    Output: `Cache cleared`

## Options
- **Daemon (`dns-rproxy.py`)**:
  - `--debug`: Enable detailed debug logging (default: INFO level).
    ```bash
    sudo python3 dns-rproxy.py --debug
    ```

- **Admin Client (`cm.py`)**:
  - `status`: Display cached queries, their expiration times, and remaining seconds.
  - `clear`: Clear the cache.

## Configuration
- **File**: `/etc/dns.config`
- **Format**: One server per line: `<IP> <priority>`
- **Notes**:
  - Lower priority numbers indicate higher priority (e.g., `1` is queried first).
  - Only successful resolutions are cached (based on minimum TTL).
  - Non-successful responses (NXDOMAIN, SERVFAIL, timeouts) are not cached.

## Notes
- **Port Requirements**: The daemon binds to UDP port 53 for DNS and TCP port 5353 (localhost) for admin commands. Run as root for port 53, or modify `LISTEN_PORT` in `dns-rproxy.py` for testing.
- **Logging**: Debug logs show query details, cache hits, and upstream responses. For production, consider logging to a file by modifying `logging.basicConfig`.
- **Cache**: In-memory, non-persistent. For high load, consider adding a size limit or external cache (e.g., Redis).

## Troubleshooting
- **Permission Errors**: Ensure the daemon runs as root for port 53.
- **ID Mismatch**: Cached responses have their IDs updated to match incoming queries.
- **Slow Responses**: Parallel querying minimizes delays (max ~5s per query).
- Check logs (`--debug`) for errors or unexpected upstream behavior.

## License
MIT License (or specify your preferred license).

