from best_download import download_file

def main():
    url = "http://speedcheck.cdn.on.net/1000meg.test"
    local_file_path = "1000meg.test"
    checksum = "cfab8f3761126268a6715f90796a68074c3f57c3af48e0101776d211e7b5139e"

    print(f"Testing download of file {url} to {local_file_path}")
    print("Please cancel half way through and re-run this example to test resuming")
    download_file(url, local_file_path, checksum)

if __name__ == '__main__':
    main()

