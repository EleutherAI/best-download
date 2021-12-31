import sys
import pickle
from signal import SIGINT
import signal
import os
from pathlib import Path
from urllib.parse import urlparse
import time

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
        if "Content-Length" in response.headers:
            content_length = int(response.headers['Content-Length'])
        accept_ranges = (response.headers.get("Accept-Ranges") == "bytes")
        return accept_ranges, content_length
    except Exception as ex:
        logger.info(f"HEAD Request Error: {ex}")
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
                file_out.write(chunk)
                checksum.update(chunk)
                progress.update(len(chunk))

    except KeyboardInterrupt as ex:
        raise ex
    except Exception as ex:
        logger.info(f"Download error: {ex}")
        return None

    return checksum.hexdigest()

class SigintHandler():
    def __init__(self):
        self.terminate = False
        handler_wrapper = lambda x,y: self.handler(x,y)
        self.previous_signal_int = signal.signal(SIGINT, handler_wrapper)

    def handler(self, signal_received, frame):
        self.terminate = True

    def release(self):
        signal.signal(SIGINT, self.previous_signal_int)

def download_file_resumable(url, local_file, content_length):

    # Handle sigint manually to avoid checkpoint corruption
    sigint_handler = SigintHandler() 

    # Always go off the checkpoint as the file was flushed before writing.
    download_checkpoint = local_file + ".ckpnt"
    try:
        resume_point, checksum = pickle.load(open(download_checkpoint, "rb"))   
        assert os.path.exists(local_file) # catch checkpoint without file
        logger.info("File already exists, resuming download.")
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
                if sigint_handler.terminate: 
                    raise KeyboardInterrupt

                file_out.write(chunk)
                file_out.flush()
                resume_point += len(chunk)
                checksum.update(chunk)                        
                pickle.dump((resume_point, checksum), open(download_checkpoint,"wb"))
                progress.update(len(chunk))

            # Only remove checkpoint at full size in case connection cut
            if os.path.getsize(local_file) == content_length:
                os.remove(download_checkpoint)
            else:
                return None

    except KeyboardInterrupt as ex:
        raise ex
    except Exception as ex:
        logger.info(f"Download error: {ex}")
        return None
    finally:
        sigint_handler.release()

    return checksum.hexdigest()

# In order to avoid leaving extra garbage meta files behind this will 
# will overwrite any existing files found at local_file. If you don't want this
# behaviour you can handle this externally.
# local_file and local_directory could write to unexpected places if the source 
# is untrusted, be careful!
def download_file(urls, expected_checksum=None, local_file=None, local_directory=None, 
                  max_retries=3):

    if not isinstance(urls, list):
        urls = [urls]

    success = False
    try:
        for url in urls:
            # Need to rebuild local_file_final each time in case of different urls
            if not local_file:        
                specific_local_file = os.path.basename(urlparse(url).path)
            else:
                specific_local_file = local_file

            if local_directory:
                os.makedirs(local_directory, exist_ok=True)
                specific_local_file = os.path.join(local_directory, specific_local_file)

            accept_ranges, content_length = get_file_info_from_server(url)
            logger.info(f"Accept-Ranges: {accept_ranges}. content length: {content_length}")
            if accept_ranges and content_length:
                download_method = download_file_resumable
                logger.info("Server supports resume")
            else:
                download_method = download_file_full
                logger.info(f"Server doesn't support resume.")
            
            for i in range(max_retries):
                logger.info(f"Download Attempt {i+1}")
                checksum = download_method(url, specific_local_file, content_length)
                if checksum:                    
                    match = ""
                    if expected_checksum:
                        match = ", Checksum Match"

                    if expected_checksum and expected_checksum != checksum:
                        logger.info(f"Checksum doesn't match. Calculated {checksum} Expecting: {expected_checksum}")                            
                    else:
                        logger.info(f"Download successful{match}. Checksum {checksum}")
                        success = True
                        break
                time.sleep(1)

            if success:
                break
            else:
                logger.info(f"Failed downloading url '{url}'")

    except KeyboardInterrupt as ex:
        logger.info('SIGINT or CTRL-C detected, stopping.')
        raise ex
    except Exception as ex: 
        logger.info(f"Unexpected Error: {ex}") # Only from block above
    
    return success
