#!/usr/local/bin/python
import sys
import os

tablefile = "/var/db/denyhosts"

def main(argv):
    new_ip = argv[0]
    f = open(tablefile, 'a')
    f.write(new_ip + '\n')
    f.close
    os.system('pfctl -t denyhosts -T add ' + new_ip)

if __name__ == "__main__":
    main(sys.argv[1:])