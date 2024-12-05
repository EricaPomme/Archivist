### README: CHECK CONFIGURATION SECTION BELOW DEFINITIONS ###

import hashlib
import os
from pathlib import Path
import argparse
import shutil
import sys
import time

class Logfile(object):
    def __init__(self, path: Path):
        self.path = path
        self.path_checksum = path / 'sha256sums.txt'
        self.path_errors = path / 'errors.log'
        try:
            self.fd_checksum = open(self.path_checksum, 'a', encoding='utf8')
        except Exception as e:
            print(f"Error creating checksum file for {path}: {e}", file=sys.stderr)
            sys.exit(1)
        try:
            self.fd_errors = open(self.path_errors, 'a', encoding='utf8')
        except Exception as e:
            print(f"Error creating error log file for {path}: {e}", file=sys.stderr)
            sys.exit(1)

    def add_checksum(self, path: Path, checksum: str) -> bool:
        global PATH_SRC
        try:
            self.fd_checksum.write(f"{checksum} *{path.relative_to(PATH_SRC)}\n")
            self.fd_checksum.flush()
            return True
        except Exception as e:
            self.add_error(path, f"Error adding checksum: {e}")
            return False
    def add_error(self, path: Path, error: str) -> bool:
        try:
            self.fd_errors.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {error} - {path.resolve()}\n")
            self.fd_errors.flush()
            return True
        except Exception as e:
            print(f"Error writing error to {self.path}: {e}", file=sys.stderr)
            return False
    
    def close(self):
        self.fd_checksum.flush()
        os.fsync(self.fd_checksum.fileno())
        self.fd_checksum.close()
        self.fd_errors.flush()
        os.fsync(self.fd_errors.fileno())
        self.fd_errors.close()

        # Remove empty logs
        if self.path_checksum.lstat().st_size == 0:
            self.path_checksum.unlink(missing_ok=True)
        if self.path_errors.lstat().st_size == 0:
            self.path_errors.unlink(missing_ok=True)
        
### BEGIN CONFIGURATION ###
PATH_SRC = Path().home() / 'Downloads'
PATH_DEST = [
    Path('/', 'Volumes', 'ARCHIVE_0'),
    Path('/', 'Volumes', 'ARCHIVE_1')
]
EXTENSIONS = [
    'jpg',
    'heic'
]
EXTENSIONS = [f".{ext}" for ext in EXTENSIONS if not ext.startswith(".")]
LOGS = [Logfile(p) for p in PATH_DEST]
REMOVE_AFTER_COPY = False
CHUNK_SIZE = 1024 * 1024  # 1MB
### END CONFIGURATION ###

# Test if paths exist and work as expected
def check_path(path, is_source=True):
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")
    if is_source and not os.access(path, os.R_OK):
        raise ValueError(f"Insufficient permissions to read from: {path}")
    if not is_source and not os.access(path, os.W_OK):
        raise ValueError(f"Insufficient permissions to write to: {path}")

try:
    check_path(PATH_SRC, is_source=True)
    for p in PATH_DEST:
        check_path(p, is_source=False)
except ValueError as e:
    print(f"Error: {e}")
    for log in LOGS:
        log.close()
    sys.exit(1)

# Build a list of files to copy
to_copy = []
for f in PATH_SRC.rglob('*'):
    if f.is_file() and f.suffix.lower() in EXTENSIONS:
        if not os.access(f, os.R_OK):
            for log in LOGS:
                log.add_error(f, "Insufficient permissions to read from")
            continue
        to_copy.append(f)

# Copy files to destination
for f in to_copy:
    checksum = hashlib.sha256()
    _outputs = []
    for p in PATH_DEST:
        if shutil.disk_usage(p).free < f.stat().st_size:
            for log in LOGS:
                log.add_error(f, f"Insufficient space in destination {p}")
            print(f"Error: Insufficient space in destination {p} for file {f}")
            sys.exit(1)
    for p in PATH_DEST:
        dest_file = p / f.relative_to(PATH_SRC)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        _outputs.append(open(dest_file, 'wb'))
    _input = open(f, 'rb')
    while True:
        chunk = _input.read(CHUNK_SIZE)
        if not chunk:
            break
        checksum.update(chunk)
        for output in _outputs:
            output.write(chunk)
    
    _input.close()
    for output in _outputs:
        output.close()
    
    checksum_hex = checksum.hexdigest()
    for log in LOGS:
        log.add_checksum(f, checksum_hex)
    
    if REMOVE_AFTER_COPY:
        try:
            f.unlink()
        except OSError as e:
            for log in LOGS:
                log.add_error(f, f"Failed to remove file: {e}")

# Cleanup
for log in LOGS:
    log.close()