from best_download import download_file
import shutil
import random
import struct
from flask import Flask, send_from_directory, request, Response
import requests
import os
from multiprocessing import Process, TimeoutError, Value
import time
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from requests.exceptions import Timeout
import pytest
import http.server
import socketserver
import re

import logging
logger = logging.getLogger(__name__)

# ================ SUPPORT ================ #
subdir = "test_data"
test_file_name = "100mb.test"
file_directory = os.path.dirname(os.path.abspath(__file__)) # script dir
test_file_path = os.path.join(file_directory, test_file_name)

hello_world_text = "<p>Hello, World!</p>"

@pytest.fixture(scope="module")
def test_100mb_file():
    logger.info(f"Building {test_file_path}")
    file_size = 104857600
    with open(test_file_path, "wb") as fh:
        for i in range(int(file_size / 8)):
            fh.write(struct.pack("Q", random.randint(0, 18446744073709551615)))
    logger.info("Yielding test_file_path")
    yield test_file_path
    logger.info("Removing test_file_path")    
    os.remove(test_file_path)

# ---------------- Raw Server (For No Head) ---------------- #
class NoHeadHandler(BaseHTTPRequestHandler):

    def do_HEAD(self):
        logger.info("raw server head")
        self.send_response(503)
        self.end_headers()

    def do_GET(self):
        logger.info("raw server get")
        self.send_response(302)
        self.send_header("Location", "http://localhost:5000/no_head")
        self.end_headers()

def server_no_head():
    hostName = "localhost"
    serverPort = 5001

    webServer = HTTPServer((hostName, serverPort), NoHeadHandler)
    logger.info("Server started http://%s:%s" % (hostName, serverPort))

    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass

    webServer.server_close()
    logger.info("Server stopped.")

go_slow = False

class AcceptRangesHandler(BaseHTTPRequestHandler):
    serve_file_path = f"/{test_file_name}"

    def do_HEAD(self):
        serve_file_size = os.path.getsize(test_file_path)
        logger.info("Fancy server head")        
        logger.info(f"URL: {self.path}")
        if self.path == self.serve_file_path:
            logger.info("Winning!")
        else: 
            logger.info("Invalid URL")
            self.send_response(404)
            self.end_headers()
            return

        headers = {key:value for key, value in self.headers.items()}
        self.send_response(200)        
        self.send_header("Accept-Ranges", "bytes")      
        self.send_header("Content-Length", str(serve_file_size))        
        self.end_headers()        

    def do_GET(self):
        global go_slow
        serve_file_size = os.path.getsize(test_file_path)
        logger.info("fancy server get")
        logger.info(f"URL: {self.path}")
        logger.info(f"Headers: {self.headers}")

        if self.path == self.serve_file_path:
            logger.info("Winning!")
        elif self.path == "/go_slow":
            go_slow = True
            self.send_response(200)
            self.end_headers()
            return
        else: 
            logger.info("Invalid URL")
            self.send_response(404)
            self.end_headers()
            return

        headers = {key:value for key, value in self.headers.items()}
        if "Range" not in headers:
            logger.info("This server is only for ranges")
            self.send_response(503)
            self.end_headers()
            return
        else:
            logger.info(headers["Range"])
            if headers["Range"][-1] == "-": # No end
                regexp = re.compile("^bytes=(?P<bytes_start>\\d*)-")
                re_match = regexp.match(headers["Range"])
                bytes_start = int(re_match.group("bytes_start"))
                if bytes_start < 0 or bytes_start > serve_file_size - 1:
                    self.send_response(503)
                    self.end_headers()

                bytes_end = serve_file_size - 1
                content_length = serve_file_size - bytes_start
                self.send_response(200)
                logger.info(f"Content-Range: bytes {bytes_start}-{bytes_end}/{serve_file_size}")
                self.send_header("Content-Range", f"bytes {bytes_start}-{bytes_end}/{serve_file_size}")
                logger.info(f"Content-Length: {content_length}")
                self.send_header("Content-Length", f"{content_length}")
                self.end_headers()
                full_file = open(test_file_path, "rb").read()
                file_slice = full_file[bytes_start:]
                if not go_slow:
                    logger.info("Not chunking")
                    self.wfile.write(file_slice) # send all
                else:
                    logger.info("Chunking")                    
                    for chunk in get_chunks(file_slice, 5):
                        self.wfile.write(chunk) # send chunk
                        logger.info("Send chunko")
                    go_slow = False
                return

            else:
                pass # No need to support                
                # regexp = re.compile("^bytes=(?P<bytes_start>\\d*)-(?P<bytes_end>\\d*)")
                # logger.info(headers["Range"])
                # re_match = regexp.match(headers["Range"])
                # logger.info(re_match)
                # bytes_start = re_match.group("bytes_start")
                # bytes_end = re_match.group("bytes_end")
                # logger.info(f"Bytes: {bytes_start}-{bytes_end}")
                # if bytes_start < 0 or bytes_start > serve_file_size - 1:
                #     self.send_response(503)
                #     self.end_headers()

                # if bytes_end < 0 or bytes_start > serve_file_size - 1:
                #     self.send_response(503)
                #     self.end_headers()

def server_accept_ranges():
    hostName = "localhost"
    serverPort = 5001

    webServer = HTTPServer((hostName, serverPort), AcceptRangesHandler)
    logger.info("Server started http://%s:%s" % (hostName, serverPort))

    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass

    webServer.server_close()
    logger.info("Server stopped.")


# ---------------- Flask Server (Head Available) ---------------- #

# Will sleep 1 second per chunk to delay file transmission 
def get_chunks(data, chunks_needed):
    logger.info("Commence chunking")
    chunk_size = int(len(data) / chunks_needed)
    start = 0
    end = min(start + chunk_size, len(data))
    while True:
        chunk = data[start:end]
        yield chunk
        if end == len(data):
            break
        time.sleep(1)
        start += chunk_size
        end = min(start + chunk_size, len(data))

def flask_server():
    app = Flask(__name__)

    @app.route("/")
    def hello_world():
        return hello_world_text

    @app.route("/basic_test")
    def basic_test():
        return send_from_directory(file_directory, test_file_name)

    @app.route("/100mb.test")
    def auto_local_file():
        return send_from_directory(file_directory, test_file_name)

    @app.route("/slow_send_for_interrupting")
    def slow_send_for_interrupting():
        # 5 second total send
        return app.response_class(get_chunks(open(test_file_path,"rb").read(), 5), mimetype="application/octet-stream")

    @app.route("/no_head")
    def no_head_test():
        return send_from_directory(file_directory, test_file_name)

    app.run(debug=False)

class RunServer:
    p = None   
    function = None

    def __init__(self, function):
        self.function = function

    def __enter__(self):       
        self.p = Process(target=self.function)
        self.p.start()
        if self.function == flask_server:
            wait_url = "http://localhost:5000"
            request_func = requests.get
        elif self.function == server_no_head:
            wait_url = "http://localhost:5001/no_head"
            request_func = requests.head
        elif self.function == server_accept_ranges:
            wait_url = "http://localhost:5001/100mb.test"
            request_func = requests.head

        logger.info(f"Polling for server startup {wait_url}...")
        while True:
            try:
                request_func(wait_url, timeout=1)
                break
            except Exception as ex:
                time.sleep(1)

        logger.info("Server online!")

    def __exit__(self, exc_type, exc_value, traceback):
        self.p.terminate()


# ================ Testception ================ #
def test_chunking(test_100mb_file):
    file_size = os.path.getsize(test_100mb_file)
    total_size = 0
    reconstructed = b""
    with open(test_100mb_file, "rb") as fh:
        original = fh.read()
    for chunk in get_chunks(original, 5):
        total_size += len(chunk)
        reconstructed += chunk

    assert(file_size == total_size)
    assert(reconstructed == original)

def test_flask_server():
    logger.info("testing flask server")
    with RunServer(function=flask_server) as fs:
        url = "http://localhost:5000"
        result = requests.get(url)
        assert(result.text == hello_world_text)

def test_server_no_head():
    with RunServer(function=server_no_head) as s:
        url = "http://localhost:5001/no_head"
        result = requests.head(url)
        assert(result.status_code == 503)

# We only test one sided ranges as that's all we use when downloading
def test_server_accept_ranges(test_100mb_file):
    with RunServer(function=server_accept_ranges) as s:
        file_size = os.path.getsize(test_file_path)

        url = "http://localhost:5001/100mb.test"
        result = requests.head(url)
        assert result.status_code == 200
        assert result.headers["Accept-Ranges"] == "bytes"
        assert result.headers["Content-Length"] == str(file_size)

        url = "http://localhost:5001/100mb.test"
        headers = {"Range":f"bytes=0-"} # Start of range

        result = requests.get(url) # No headers
        assert result.status_code == 503

        result = requests.get(url, headers=headers)
        assert result.status_code == 200

        # Outside of range
        headers = {"Range":f"bytes={file_size}-"}
        result = requests.get(url, headers=headers)
        assert result.status_code == 503

        # Just inside of range
        bytes_start = file_size-1
        bytes_end = file_size - 1
        content_length = file_size - bytes_start
        headers = {"Range":f"bytes={bytes_start}-"}
        result = requests.get(url, headers=headers)
        assert result.status_code == 200
        logger.info(result.headers)
        assert result.headers["Content-Length"] == f"{content_length}"
        assert result.headers["Content-Range"] == f"bytes {bytes_start}-{bytes_end}/{file_size}"
        assert len(result.content) == content_length        
        logger.info(f"Body Length: {len(result.content)}")

        # Middle of range
        bytes_start = int(file_size/2)
        bytes_end = file_size - 1
        content_length = file_size - bytes_start
        headers = {"Range":f"bytes={bytes_start}-"}
        result = requests.get(url, headers=headers)
        assert result.status_code == 200
        logger.info(result.headers)
        assert result.headers["Content-Length"] == f"{content_length}"
        assert result.headers["Content-Range"] == f"bytes {bytes_start}-{bytes_end}/{file_size}"
        assert len(result.content) == content_length
        logger.info(f"Body Length: {len(result.content)}")


# # ================ Best Download Tests ================ #
@pytest.fixture
def expected_checksum(test_100mb_file):
    hasher = hashlib.sha256()
    with open(test_100mb_file, "rb") as fh:
        data = fh.read()
        hasher.update(data)
        return hasher.hexdigest()

@pytest.fixture
def local_directory():
    os.makedirs(subdir, exist_ok=True)
    yield subdir
    os.rmdir(subdir)

def test_no_gzip():
    url = "https://raw.githubusercontent.com/openai/gpt-3/master/data/two_digit_addition.jsonl"
    local_file = "two_digit_addition.jsonl"
    checksum = "75a54b7a3db3b23369df74fe440c23025f3d3c51f664300bd3d56632b2617b3d"
    assert download_file(url, expected_checksum=checksum)
    assert os.path.exists(local_file)
    os.remove(local_file)

# A little bit slow - comment out if needed
def test_remote_server():
    checksum = "cc844cac4b2310321d0fd1f9945520e2c08a95cefd6b828d78cdf306b4990b3a"
    url = "http://ipv4.download.thinkbroadband.com/100MB.zip"
    assert download_file(url, expected_checksum=checksum)
    assert os.path.exists("100MB.zip")
    os.remove("100MB.zip")

def test_accept_ranges(expected_checksum):
    logger.info(f"Expected Checksum: {expected_checksum}")        

    with RunServer(function=server_accept_ranges) as fs:
        url = "http://localhost:5001/100mb.test"
        assert download_file(url, expected_checksum=expected_checksum, local_file=test_file_name)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

def do_download(url, out_file, expected_checksum, result):
    result.value = download_file(url, expected_checksum=expected_checksum, local_file=out_file)

def test_interrupted_resume(expected_checksum):
    logger.info(f"Expected Checksum: {expected_checksum}")

    download_result = Value('i', -1) # Shared memory for download process
    with RunServer(function=server_accept_ranges) as fs:

        # Sets a flag in fancy server for next request
        url = "http://localhost:5001/go_slow"
        result = requests.get(url)
        assert result.status_code == 200

        url = "http://localhost:5001/100mb.test"
        download_process = Process(target=do_download, args=(url, test_file_name, expected_checksum, download_result))
        download_process.start()
        time.sleep(2.5) # Leave block half way through and kill server

    time.sleep(2) # I think the fancy server needs some time between startups (port lock?)

    # Restart server
    with RunServer(function=server_accept_ranges) as fs:
        logger.info("Attempting join")
        download_process.join(timeout=30)
        logger.info(download_result.value)
        assert(download_result.value == 1)

    assert os.path.exists(test_file_name)
    os.remove(test_file_name)

# This will just restart the download as flask doesn't support resuming
def test_interrupted(expected_checksum):
    logger.info(f"Expected Checksum: {expected_checksum}")        

    result = Value('i', -1)
    with RunServer(function=flask_server) as fs:
        url = "http://localhost:5000/slow_send_for_interrupting"
        download_process = Process(target=do_download, args=(url, test_file_name, expected_checksum, result))
        download_process.start()
        time.sleep(2.5) # Leave block half way through and kill server

    # Restart server
    with RunServer(function=flask_server) as fs:
        logger.info("Attempting join")
        download_process.join(timeout=30)
        logger.info(result.value)
        assert(result.value == 1)

    assert os.path.exists(test_file_name)
    os.remove(test_file_name)

def test_same_url(expected_checksum, local_directory):
    logger.info(f"Expected Checksum: {expected_checksum}")        

    with RunServer(function=flask_server) as fs:
        url = "http://localhost:5000/100mb.test"
        assert download_file(url, expected_checksum=expected_checksum, local_file=test_file_name)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

        assert download_file(url, expected_checksum=expected_checksum)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

        assert download_file(url, expected_checksum=expected_checksum, local_file=test_file_name, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert os.path.exists(local_file)
        os.remove(local_file)

        assert download_file(url, expected_checksum=expected_checksum, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert os.path.exists(local_file)
        os.remove(local_file)

def test_different_url(expected_checksum, local_directory):
    logger.info(f"Expected Checksum: {expected_checksum}")        

    with RunServer(function=flask_server) as fs:
        url = "http://localhost:5000/basic_test"
        assert download_file(url, expected_checksum=expected_checksum, local_file=test_file_name)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

        assert download_file(url, expected_checksum=expected_checksum)
        assert not os.path.exists(test_file_name)
        assert os.path.exists("basic_test")
        os.remove("basic_test")

        assert download_file(url, expected_checksum=expected_checksum, local_file=test_file_name, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert os.path.exists(local_file)
        os.remove(local_file)

        assert download_file(url, expected_checksum=expected_checksum, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, "basic_test")
        auto_local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert not os.path.exists(auto_local_file)
        assert os.path.exists(local_file)
        os.remove(local_file)

def test_multiple_urls(expected_checksum, local_directory):
    logger.info(f"Expected Checksum: {expected_checksum}")        

    with RunServer(function=flask_server) as fs:
        # Test valid first url        
        urls = ["http://localhost:5000/100mb.test", "http://localhost:5000/basic_test"]
        assert download_file(urls, expected_checksum=expected_checksum, local_file=test_file_name)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

        assert download_file(urls, expected_checksum=expected_checksum)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

        assert download_file(urls, expected_checksum=expected_checksum, local_file=test_file_name, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert os.path.exists(local_file)
        os.remove(local_file)

        assert download_file(urls, expected_checksum=expected_checksum, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert os.path.exists(local_file)
        os.remove(local_file)

        # Test valid first url
        urls = ["http://localhost:5000/basic_test", "http://localhost:5000/100mb.test"]
        assert download_file(urls, expected_checksum=expected_checksum, local_file=test_file_name)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

        assert download_file(urls, expected_checksum=expected_checksum)
        assert not os.path.exists(test_file_name)
        assert os.path.exists("basic_test")
        os.remove("basic_test")

        assert download_file(urls, expected_checksum=expected_checksum, local_file=test_file_name, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert os.path.exists(local_file)
        os.remove(local_file)

        assert download_file(urls, expected_checksum=expected_checksum, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, "basic_test")
        auto_local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert not os.path.exists(auto_local_file)
        assert os.path.exists(local_file)
        os.remove(local_file)

        # Failover Test
        urls = ["http://localhost:5000/invalid", "http://localhost:5000/100mb.test"]
        assert download_file(urls, expected_checksum=expected_checksum, local_file=test_file_name)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

        assert download_file(urls, expected_checksum=expected_checksum)
        assert os.path.exists(test_file_name)
        os.remove(test_file_name)

        assert download_file(urls, expected_checksum=expected_checksum, local_file=test_file_name, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert os.path.exists(local_file)
        os.remove(local_file)

        assert download_file(urls, expected_checksum=expected_checksum, 
                             local_directory=local_directory)
        local_file = os.path.join(local_directory, test_file_name)
        assert not os.path.exists(test_file_name)
        assert os.path.exists(local_file)
        os.remove(local_file)

        # Wasn't sure whether to clear failed downloads - simpler just to leave I think
        os.remove("invalid")
        os.remove(os.path.join(local_directory,"invalid"))

def test_no_head(expected_checksum):
    logger.info(f"Expected Checksum: {expected_checksum}")

    # No idea how to handle head requests in flask - use http.server for head and redirect on the get
    with RunServer(function=server_no_head) as s:
        with RunServer(function=flask_server) as fs:
            url = "http://localhost:5001/no_head"
            assert download_file(url, expected_checksum=expected_checksum, local_file=test_file_name)
            assert os.path.exists(test_file_name)
            os.remove(test_file_name)        