import sys
import pickle
from signal import SIGINT
import signal
import os
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import rehash
from tqdm import tqdm

import logging
logger = logging.getLogger(__name__)

# Head request to get file-length and check whether it supports ranges.
def get_file_info_from_server(url):
    try:
        headers={"Accept-Encoding": "identity"} # Avoid dealing with gzip
        response = requests.head(url, headers=headers) 
        response.raise_for_status()
        content_length = None
        # tqdm.write(f"{response.headers}")
        if "Content-Length" in response.headers:
            content_length = int(response.headers['Content-Length'])
        accept_ranges = (response.headers.get("Accept-Ranges") == "bytes")
        return accept_ranges, content_length
    except Exception as ex:
        tqdm.write(f"HEAD Request Error: {ex}")
        return False, None

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

chunk_size = 1024*1024

def download_file_full(url, local_file, content_length):
    try:
        checksum = rehash.sha256()
        headers = {"Accept-Encoding": "identity"} # Avoid dealing with gzip
        with tqdm(total=content_length, unit="byte", unit_scale=1) as progress, \
             session.get(url, headers=headers, stream=True, timeout=5) as response, \
             open(local_file, 'wb') as file_out:

            response.raise_for_status()

            for chunk in response.iter_content(chunk_size):
                if terminate:
                    sys.exit(0)

                file_out.write(chunk)
                checksum.update(chunk)
                progress.update(len(chunk))

    except Exception as ex:
        tqdm.write(f"Download error: {ex}")
        return None

    return checksum.hexdigest()

def download_file_resumable(url, local_file, content_length):
    # Always go off the checkpoint as the file was flushed before writing.
    download_checkpoint = local_file + ".ckpnt"
    try:
        resume_point, checksum = pickle.load(open(download_checkpoint, "rb"))
        tqdm.write("File already exists, resuming download.")
    except:
        resume_point = 0
        checksum = rehash.sha256()
        if os.path.exists(local_file):
            os.remove(local_file)
        Path(local_file).touch()

    assert (resume_point < content_length)

    # Support resuming
    headers = {}
    headers["Range"] = f"bytes={resume_point}-"
    headers["Accept-Encoding"] = "identity" # Avoid dealing with gzip

    try:
        with tqdm(total=content_length, unit="byte", unit_scale=1) as progress, \
             session.get(url, headers=headers, stream=True, timeout=5) as response, \
             open(local_file, 'r+b') as file_out:

            response.raise_for_status()
            progress.update(resume_point)
            file_out.seek(resume_point)

            for chunk in response.iter_content(chunk_size):
                if terminate:
                    sys.exit(0)

                file_out.write(chunk)
                file_out.flush()
                resume_point += len(chunk)
                checksum.update(chunk)                        
                pickle.dump((resume_point, checksum), open(download_checkpoint,"wb"))
                progress.update(len(chunk))

            os.remove(download_checkpoint)

    except Exception as ex:
        tqdm.write(f"Download error: {ex}")
        return False

    return checksum.hexdigest()

# In order to avoid leaving extra garbage meta files behind this will 
# will overwrite any existing files found at local_file. If you don't want this
# behaviour you can handle this externally.
def download_file(url, local_file, expected_checksum=None):
    # Handle SIGINT nicely
    previous_signal_int = signal.signal(SIGINT, handler)

    success = False
    try:
        max_retries = 3
        accept_ranges, content_length = get_file_info_from_server(url)
        if accept_ranges and content_length:
            download_method = download_file_resumable
            tqdm.write("Server supports resume")
        else:
            download_method = download_file_full
            tqdm.write("Server doesn't support resume")
        
        for i in range(max_retries):
            checksum = download_method(url, local_file, content_length)
            if checksum:
                tqdm.write(f"File downloaded. Checksum: {checksum}")
                if expected_checksum and expected_checksum != checksum:
                    tqdm.write(f"Checksum doesn't match. Expecting: {expected_checksum}")
                    continue

                success = True
                break

    except Exception as ex:
        tqdm.write(f"Unexpected Error: {ex}")
    finally:
        if terminate:
            tqdm.write('SIGINT or CTRL-C detected, stopping.')

        signal.signal(SIGINT, previous_signal_int)
        return success
