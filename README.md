# best-download
URL downloader supporting checkpointing and continuous checksumming.

We take over handling of SIGINT for cleaner messaging, this is reverted once downloading is complete. If you already handle SIGINT yourself please make a fork.

NOTE: When the local_file already exists we automatically overwrite unless there is a checkpoint file there. When the download successfully completes the checkpoint will be deleted and True returned. This avoids leaving rubbish in the file system or doing full checksum calculations for large files. You will need to manage existing files if your scripts are re-runnable, either maintain your own database/done files or do a manual checksum.

## Install
```bash
pip install best-download
```

## Basic Example
The following example can be found in "examples/basic_example.py". There are some example urls in the tests array, including a test case for a server not supporting ranges (github).

```python
from best_download import download_file

tests = []
tests.append(("http://speedcheck.cdn.on.net/100meg.test", "100meg.test",
    "b89222456931da603c4c601208b6bf9d1a0d7cad3bde957163612074b04e6154"))
tests.append(("http://speedcheck.cdn.on.net/1000meg.test", "1000meg.test",
    "cfab8f3761126268a6715f90796a68074c3f57c3af48e0101776d211e7b5139e"))

# Github example doesn't support resuming
tests.append(("https://github.com/Nealcly/MuTual/archive/master.zip", "master.zip", None))

def main():
    url, local_file_path, checksum = tests[0]

    print(f"Testing download of file {url} to {local_file_path}")
    print("Please cancel half way through and re-run this example to test resuming")
    download_file(url, local_file_path, checksum)

if __name__ == '__main__':
    main()
```
