import sys
import pickle
from signal import SIGINT
import signal
import os

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import rehash
from tqdm import tqdm

def get_url_content_length(url):
    response = requests.head(url)
    response.raise_for_status()

    if "Content-Length" in response.headers:
        return int(response.headers['Content-length'])
    else:
        return None

# Support 3 retries and backoff
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    method_whitelist=["HEAD", "GET", "OPTIONS"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session = requests.Session()
session.mount("https://", adapter)
session.mount("http://", adapter)

terminate = False
def handler(signal_received, frame):
    global terminate
    terminate = True

def download_file(url, to, checksum=None):
    # Handle SIGINT nicely
    previous_signal_int = signal.signal(SIGINT, handler)

    try:
        tqdm.write('Downloading {}'.format(url))
        expected_size = get_url_content_length(url)
        # print(f"Expected Size: {expected_size}")

        max_retries = 3
        fail_count = 0
        download_checkpoint = to + ".ckpnt"
        while True:
            resume_point = 0
            temp_checksum = rehash.sha256()
            if os.path.exists(to):
                # print(f"File Size: {os.path.getsize(to)}")

                # Load checkpoint if available
                try:
                    resume_point, temp_checksum = pickle.load(open(download_checkpoint, "rb"))
                except:
                    resume_point = os.path.getsize(to)
                    temp_checksum = rehash.sha256()
                    with open(to, "rb") as f:
                        for byte_block in iter(lambda: f.read(4096),b""):
                            if terminate:
                                sys.exit(0)
                            temp_checksum.update(byte_block)

                if expected_size and os.path.getsize(to) != expected_size:
                    pass # Will resume below
                else:
                    # No size info or full size
                    if checksum:
                        if temp_checksum.hexdigest() == checksum:
                            tqdm.write(f"Checksum OK")
                            return
                        else:
                            fail_count += 1
                    else:
                        tqdm.write("Comparison checksum not available")
                        tqdm.write(f"sha256: {temp_checksum.hexdigest()}")
                        return

            chunk_size = 1024*1024
            with tqdm(total=expected_size, unit="byte", unit_scale=1) as progress:
                try:
                    # Support resuming
                    if os.path.exists(to):
                        tqdm.write("File already exists, resuming download.")
                        headers = {}
                        headers["Range"] = f"bytes={resume_point}-"
                        progress.update(resume_point)
                    else:
                        headers=None

                    with session.get(url, headers=headers, stream=True) as r, \
                         open(to, 'ab') as f:

                        f.seek(resume_point)
                        r.raise_for_status()
                        for chunk in r.iter_content(chunk_size):
                            if terminate:
                                sys.exit(0)

                            f.write(chunk)

                            chunk_length = len(chunk)                        
                            resume_point += chunk_length
                            temp_checksum.update(chunk)                        
                            pickle.dump((resume_point, temp_checksum), open(download_checkpoint,"wb"))

                            progress.update(chunk_length)

                except Exception as ex:
                    tqdm.write(f"Download error: {ex}")
                    fail_count += 1
                
            if fail_count == max_retries:
                raise Exception("Download failed")
    finally:
        if terminate:
            tqdm.write('SIGINT or CTRL-C detected, stopping.')

        signal.signal(SIGINT, previous_signal_int)