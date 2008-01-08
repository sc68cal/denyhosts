#!/usr/local/bin/python
import sys
import os
import re

tablefile = "/var/db/denyhosts"

def main(argv):
    f = open(tablefile, 'r')
    ip_check = re.compile("\s*" + argv[0] + ".*")
    ips = f.readlines()
    f.close()
    new_ips = [i for i in ips if not ip_check.match(i)]
    f = open(tablefile, 'w')
    f.writelines(new_ips)
    f.close()
    os.system("pfctl -t denyhosts -T delete " + argv[0])

if __name__ == "__main__":
    main(sys.argv[1:])