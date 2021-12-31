# best-download
URL downloader supporting checkpointing and continuous checksumming.

NOTE: When the local_file already exists we automatically overwrite unless there is a checkpoint file there. When the download successfully completes the checkpoint will be deleted and True returned. This avoids leaving rubbish in the file system or doing full checksum calculations for large files. You will need to manage existing files if your scripts are re-runnable, either maintain your own database/done files or do a manual checksum.

## Recent Updates:
1. Added multiple urls option for failover.
2. Parameter changes to 'download_file'
- *local_file* is now optional, and will be set to the url basepath if not provided
- Added *local_directory* option, will be prepended to *local_file*. Mainly useful
  for downloading to a directory and using automatic local_file
3. Improved SIGINT handling. We now raise a KeyboardInterrupt exception after handling it safely internally.
4. Added a decent set of tests:
```
pip install -r requirements-dev.txt
pytest
```

## Install
```bash
pip install best-download
```

##  Quickstart
```python
from best_download import download_file

url = "http://ipv4.download.thinkbroadband.com/10MB.zip"
checksum = "d076d819249a9827c8a035bb059498bf49f391a989a1f7e166bc70d028025135"
local_file = "10MB.zip"
try:
  success = download_file(url, local_file=local_file, expected_checksum=checksum)
except KeyboardInterrupt:
  print("Ctrl-C (SIGINT) is passed up")
```

## API
There's only one entry point: 

```python
def download_file(urls, expected_checksum=None, local_file=None, local_directory=None, max_retries=3)
```

| Parameter      | Description |
| -----------: | ----------- |
| `urls` | Either a single url or a list of urls to iterate over if failover required. |
| `expected_checksum` | (Optional) Checksum to validate against after download complete. Will not validate if not provided. |
| `local_file` | (Optional) Output path for saving the file. If not provided we default to the url basepath. | 
| `local_directory` | (Optional) If provided will be prepended to *local_file*. Mainly useful for downloading to a directory and using automatic local_file. |
| `max_retries` | (Default: 3) Number of retry attmpts per url (per failover if list is provided). |

## Examples
The following example can be found in "examples/basic_example.py". There are some example urls in the tests array, including test cases for a server not supporting ranges (github) and a server defaulting to gzip encoding which we don't use. We demo resuming at the end.

```python
import os
from best_download import download_file

import logging
logger = logging.getLogger()
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.setLevel(logging.INFO)

tests = []
tests.append(("http://ipv4.download.thinkbroadband.com/10MB.zip", "10MB.zip",
    "d076d819249a9827c8a035bb059498bf49f391a989a1f7e166bc70d028025135"))

# Larger file used for cancel test
tests.append(("http://ipv4.download.thinkbroadband.com/100MB.zip", "100MB.zip",
    "cc844cac4b2310321d0fd1f9945520e2c08a95cefd6b828d78cdf306b4990b3a"))

# Github example doesn't support resuming
tests.append(("https://github.com/Nealcly/MuTual/archive/master.zip", "master.zip", None))

# Testing Accept-Encoding: identity (no gzip)
tests.append(("https://raw.githubusercontent.com/openai/gpt-3/master/data/two_digit_addition.jsonl",
             "two_digit_addition.jsonl", "75a54b7a3db3b23369df74fe440c23025f3d3c51f664300bd3d56632b2617b3d"))

def main():
    logger.info("Commence Demo")
    url, local_file, checksum = tests[0]

    # local_file provided
    logger.info(f"\nTesting download of file {url} to {local_file}")
    logger.info("-----------------------------------------------------------------------")
    download_file(url, local_file=local_file, expected_checksum=checksum)
    assert os.path.exists(local_file)
    os.remove(local_file)

    # local_file automatically discovered from url basepath    
    logger.info(f"\nTesting download of file {url} to {local_file} without providing local_file")
    logger.info("-----------------------------------------------------------------------")    
    download_file(url, expected_checksum=checksum)
    assert os.path.exists(local_file)
    os.remove(local_file)

    # local_directory provided
    local_directory = "testing_download"
    local_file_path = os.path.join(local_directory, local_file)
    logger.info(f"\nTesting download of file {url} to {local_file_path}")
    logger.info("-----------------------------------------------------------------------")    
    download_file(url, expected_checksum=checksum, local_file=local_file, local_directory=local_directory)
    assert os.path.exists(local_file_path)
    os.remove(local_file_path)
    os.rmdir(local_directory)

    # local_directory provided + local_file automatically discovered from url basepath
    local_directory = "testing_download"
    local_file_path = os.path.join(local_directory, local_file)
    logger.info(f"\nTesting download of file {url} to {local_file_path} without providing local_file")
    logger.info("-----------------------------------------------------------------------")    
    download_file(url, expected_checksum=checksum, local_directory=local_directory)
    assert os.path.exists(local_file_path)
    os.remove(local_file_path)
    os.rmdir(local_directory)

    # Resume Test    
    logger.info("\nResume Test")
    logger.info("-----------------------------------------------------------------------")
    url, local_file, checksum = tests[1]
    logger.info("Please cancel half way through and re-run this example to test resuming")
    try:
        download_file(url, local_file=local_file, expected_checksum=checksum)
    except KeyboardInterrupt:
        pass
    logger.info("Attempting resume if you cancelled in time.")
    download_file(url, local_file=local_file, expected_checksum=checksum)
    assert os.path.exists(local_file)
    os.remove(local_file)

if __name__ == '__main__':
    main()
```
