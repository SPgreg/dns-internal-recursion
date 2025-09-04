import socket
import dns.message
import dns.query
import dns.rdataclass
import dns.rdatatype
import dns.rcode
import logging
import time
import argparse
import concurrent.futures
import threading
import json

CONFIG_FILE = '/etc/fgdns.config'  # Configuration file path
LISTEN_ADDR = '0.0.0.0'            # Bind to all interfaces
LISTEN_PORT = 53                   # Standard DNS port
ADMIN_PORT = 5353                  # Admin TCP port (localhost only)
TIMEOUT = 5                        # Seconds per upstream query
DEFAULT_TTL = 300                  # Default TTL in seconds if no TTL found (5 minutes)

# Global cache: key = (qname, rdtype, rdclass), value = (response, expiration_time)
cache = {}

def load_config(file_path):
    servers = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments (lines starting with # or //)
                if not line or line.startswith('#') or line.startswith('//'):
                    continue
                try:
                    ip, priority = line.split()
                    servers.append((ip, int(priority)))
                except ValueError:
                    logging.warning(f"Skipping invalid line in config: {line}")
                    continue
        # Sort by priority (lowest number = highest priority)
        servers.sort(key=lambda x: x[1])
        return servers  # Return list of (ip, priority)
    except FileNotFoundError:
        logging.error(f"Config file {file_path} not found")
        return []
    except Exception as e:
        logging.error(f"Error reading config file: {e}")
        return []

def query_upstream(upstream, priority, query):
    try:
        response = dns.query.udp(query, upstream, timeout=TIMEOUT)
        return priority, response
    except Exception as e:
        logging.debug(f"Failed querying {upstream}: {e}")
        return priority, None

def handle_query(data, addr, sock, server_list):
    try:
        query = dns.message.from_wire(data)
        query_key = (str(query.question[0].name), query.question[0].rdtype, query.question[0].rdclass)
        logging.debug(f"Received query from {addr}: {query.question[0]} (key: {query_key})")

        # Check cache
        if query_key in cache:
            cached_response, expiration = cache[query_key]
            if time.time() < expiration:
                logging.debug(f"Cache hit for {query_key}")
                # Update the response ID to match the incoming query's ID
                cached_response.id = query.id
                sock.sendto(cached_response.to_wire(), addr)
                logging.debug(f"Sent cached response with updated ID {query.id}")
                return
            else:
                logging.debug(f"Cache expired for {query_key}")
                del cache[query_key]

        # Query upstreams in parallel
        min_priority = min(p for _, p in server_list) if server_list else None
        responses = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(server_list)) as executor:
            future_to_up = {executor.submit(query_upstream, ip, pri, query): ip for ip, pri in server_list}
            for future in concurrent.futures.as_completed(future_to_up):
                pri, response = future.result()
                if response and response.rcode() == dns.rcode.NOERROR and response.answer:
                    responses[pri] = response
                    if pri == min_priority:
                        # Cache and send immediately if it's the highest priority (lowest number)
                        try:
                            ttls = [rrset.ttl for rrset in response.answer]
                            min_ttl = min(ttls) if ttls else DEFAULT_TTL
                            expiration = time.time() + min_ttl
                            cache[query_key] = (response, expiration)
                            logging.debug(f"Cached response for {query_key} with min TTL {min_ttl} seconds")
                        except Exception as e:
                            logging.warning(f"Failed to cache response from priority {pri}: {e}")
                        sock.sendto(response.to_wire(), addr)
                        return

        # After all, select the best (lowest priority) among successful responses
        if responses:
            best_pri = min(responses.keys())
            response = responses[best_pri]
            # Cache if not already (though only if not min_priority)
            if query_key not in cache:
                try:
                    ttls = [rrset.ttl for rrset in response.answer]
                    min_ttl = min(ttls) if ttls else DEFAULT_TTL
                    expiration = time.time() + min_ttl
                    cache[query_key] = (response, expiration)
                    logging.debug(f"Cached response for {query_key} with min TTL {min_ttl} seconds")
                except Exception as e:
                    logging.warning(f"Failed to cache response from priority {best_pri}: {e}")
            sock.sendto(response.to_wire(), addr)
            return

        # If no successful responses, send SERVFAIL
        logging.debug("All upstreams failed or returned non-successful responses; sending SERVFAIL")
        fail_resp = dns.message.make_response(query)
        fail_resp.set_rcode(dns.rcode.SERVFAIL)
        sock.sendto(fail_resp.to_wire(), addr)
    except Exception as e:
        logging.error(f"Error handling query: {e}")

def admin_server():
    admin_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    admin_sock.bind(('127.0.0.1', ADMIN_PORT))
    admin_sock.listen(1)
    logging.info(f"Admin server listening on 127.0.0.1:{ADMIN_PORT}")
    while True:
        conn, _ = admin_sock.accept()
        try:
            data = conn.recv(1024).decode().strip()
            if data == 'status':
                status = {
                    str(key): {
                        'expiration': time.ctime(exp),
                        'remaining_seconds': int(exp - time.time())
                    } for key, (_, exp) in cache.items()
                }
                conn.send(json.dumps(status).encode())
            elif data == 'clear':
                cache.clear()
                conn.send(b'Cache cleared')
            else:
                conn.send(b'Invalid command')
        except Exception as e:
            logging.error(f"Admin server error: {e}")
        finally:
            conn.close()

def main():
    parser = argparse.ArgumentParser(description="FGDNS Proxy Daemon")
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    server_list = load_config(CONFIG_FILE)
    if not server_list:
        logging.error("No valid upstream servers loaded. Exiting.")
        return
    logging.info(f"Loaded upstreams in order: {server_list}")

    # Start admin server in a thread
    threading.Thread(target=admin_server, daemon=True).start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((LISTEN_ADDR, LISTEN_PORT))
        logging.info(f"Listening on {LISTEN_ADDR}:{LISTEN_PORT}")
        while True:
            data, addr = sock.recvfrom(1024)
            handle_query(data, addr, sock, server_list)
    except PermissionError:
        logging.error(f"Error: Cannot bind to port {LISTEN_PORT}. Run as root or use a higher port.")
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
