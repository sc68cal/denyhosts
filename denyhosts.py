#!/bin/env python
import os, sys
import re
import getopt
from smtplib import SMTP
import string

global DEBUG
DEBUG=0
CONFIG_FILE = "denyhosts.cfg"


#################################################################################
#        These files will be created relative to WORK_DIR                       #
#################################################################################
SECURE_LOG_OFFSET = "offset"
ALLOWED_HOSTS = "allowed-hosts"
#PARSED_DATES = "file_dates"
ABUSIVE_HOSTS = "hosts"
ABUSED_USERS_INVALID = "users-invalid"
ABUSED_USERS_VALID = "users-valid"
ABUSED_USERS_AND_HOSTS = "users-hosts"                              
SUSPICIOUS_LOGINS = "suspicious-logins"   # successful logins AFTER invalid
                                          #   attempts from same host

#################################################################################
# REGULAR EXPRESSIONS ARE COOL.  Check out Kodos (http://kodos.sourceforge.net) #
#################################################################################

#DATE_FORMAT_REGEX = re.compile(r"""(?P<month>[A-z]{3,3})\s*(?P<day>\d+)""")

FAILED_ENTRY_REGEX = re.compile(r""".* sshd.*: Failed password for (?P<invalid>invalid user )?(?P<user>.*?) from ::ffff:(?P<host>.*?) """)

SUCCESSFUL_ENTRY_REGEX = re.compile(r""".* sshd.*: Accepted password for (?P<user>.*?) from ::ffff:(?P<host>.*?) """)

PREFS_REGEX = re.compile(r"""(?P<name>.*?)\s*[:=]\s*(?P<value>.*)""")

ALLOWED_REGEX = re.compile(r"""(?P<first_3bits>\d{1,3}\.\d{1,3}\.\d{1,3}\.)((?P<fourth>\d{1,3})|(?P<ip_wildcard>\*)|\[(?P<ip_range>\d{1,3}\-\d{1,3})\])""")

#################################################################################

def die(msg, ex=None):
    print msg
    if ex: print ex
    sys.exit(1)


def send_email(prefs, denied_hosts, status, suspicious_logins):
    smtp = SMTP(prefs.get('SMTP_HOST'),
                prefs.get('SMTP_PORT'))

    msg = """From: %s
To: %s
Subject: %s

""" % (prefs.get('SMTP_FROM'),
       prefs.get('ADMIN_EMAIL'),
       prefs.get('SMTP_SUBJECT'))

    
    if denied_hosts:
        if not status:
            msg += "COULD NOT add the following hosts to %s:\n\n" % prefs.get('HOSTS_DENY')
        else:
            msg += "Added the following hosts to %s:\n\n" % prefs.get('HOSTS_DENY')

        for host in denied_hosts:
            msg += "%s\n" % host
        msg += "\n"

        
    if suspicious_logins:
        msg += "-" * 60 + "\n\n"
        msg += "Observed the following suspicious login activity:\n\n"
        for login in suspicious_logins:
            msg += "%s\n" % login    
        msg += "\n"
        
    smtp.sendmail(prefs.get('SMTP_FROM'),
                  prefs.get('ADMIN_EMAIL'),
                  msg)
    smtp.quit()


def usage():
    print "Usage:  %s [-f logfile | --file=logfile] [ -c configfile | --config=configfile] [-i | --ignore] [-n | --noemail]" % sys.argv[0]
    print
    print " --file:   The name of log file to parse (default is: %s)" % SECURE_LOG
    print " --ignore: Ignore last processed offset (start processing from beginning)"
    print " --noemail: Do not send an email report"
    print
    print "Note: multiple --file args can be processed. ",
    print "If provided, --ignore is implied"
    print

#################################################################################

class Prefs:
    def __init__(self, path=None):
        self.__data = {'ADMIN_EMAIL': None}
        
        self.reqd = ('DENY_THRESHOLD',
                     'SECURE_LOG',
                     'HOSTS_DENY',
                     'BLOCK_SERVICE',
                     'WORK_DIR')

        self.to_int = ('DENY_THRESHOLD', )
                
        if path: self.load_settings(path)

        
    def load_settings(self, path):
        try:
            fp = open(path, "r")
        except Exception, e :
            die("Error reading file: %s" % path, e)


        for line in fp:
            line = line.strip()
            if not line or line[0] in ('\n', '#'):
                continue
            m = PREFS_REGEX.search(line)
            if m:
                name = m.group('name').upper()
                value = m.group('value')
                #print name, value
                if not value: value = None
                if name in self.to_int:
                    value = int(value)
                self.__data[name] = value
        fp.close()
        self.check_required(path)


    def check_required(self, path):
        ok = 1
        for reqd in self.reqd:
            if not self.__data.has_key(reqd):
                print "Missing configuration parameter: %s" % reqd
                ok = 0
            elif not self.__data[reqd]:
                print "Missing configuration value for: %s" % reqd
                ok = 0

        if not ok:
            die("You must correct these problems found in: %s" % path)


    def get(self, name):
        return self.__data[name]


    def dump(self):
        print "Preferences:"
        keys = self.__data.keys()
        for key in keys:
            print "   %s: [%s]" % (key, self.__data[key])

    
#################################################################################


class FileTracker:
    def __init__(self, work_dir, logfile):
        self.work_dir = work_dir
        self.logfile = logfile
        (self.__first_line, self.__offset) = self.__get_current_offset()
        

    def __get_last_offset(self):
        path = os.path.join(self.work_dir,
                            SECURE_LOG_OFFSET)
        first_line = ""
        offset = 0L
        try:
            fp = open(path, "r")
            first_line = fp.readline()[:-1]
            offset = long(fp.readline())
        except:
            pass

        if DEBUG:
            print "__get_last_offset():"
            print "   first_line:", first_line
            print "   offset:", offset
            
        return first_line, offset


    def __get_current_offset(self):
        first_line = ""
        offset = 0L
        try:
            fp = open(self.logfile, "r")
            first_line = fp.readline()[:-1]
            fp.seek(0, 2)
            offset = fp.tell()
        except Exception, e:
            die("Can't read: %s" % self.logfile, e)

        if DEBUG:
            print "__get_current_offset():"
            print "   first_line:", first_line
            print "   offset:", offset
            
        return first_line, offset

    
    def get_offset(self):
        last_line, last_offset = self.__get_last_offset()


        if last_line != self.__first_line:
            # log file was rotated, start from beginning
            offset = 0L
        elif self.__offset > last_offset:
            # new lines exist in log file
            offset = last_offset
        else:
            # no new entries in log file
            offset = None

        if DEBUG:
            print "get_offset():"
            print "   offset:", offset
            
        return offset
    
        
    def save_offset(self, offset):
        path = os.path.join(self.work_dir,
                            SECURE_LOG_OFFSET)
        try:
            fp = open(path, "w")
            fp.write("%s\n" % self.__first_line)
            fp.write("%ld\n" % offset)
            fp.close()
        except:
            print "Could not save logfile offset to: %s" % path
            
        

#################################################################################
    

class LoginAttempt:
    def __init__(self, work_dir, deny_threshold, first_time=0):
        self.__work_dir = work_dir
        self.__deny_threshold = deny_threshold
        self.__first_time = first_time
        self.__suspicious_logins = self.get_suspicious_logins()
        self.__valid_users = self.get_abused_users_valid()
        self.__invalid_users = self.get_abused_users_invalid()
        self.__valid_users_and_hosts = self.get_abused_users_and_hosts()
        self.__abusive_hosts = self.get_abusive_hosts()

        self.__new_suspicious_logins = []


    def get_new_suspicious_logins(self):
        return self.__new_suspicious_logins

        
    def add(self, user, host, success, invalid):
        user_host_key = "%s - %s" % (user, host)

        if success and self.__abusive_hosts.get(host, 0) > self.__deny_threshold:
            num_failures = self.__valid_users_and_hosts.get(user_host_key, 0)
            try:
                self.__suspicious_logins[user_host_key] += 1
            except:
                self.__suspicious_logins[user_host_key] = 1

            self.__new_suspicious_logins.append(user_host_key)
            
        elif not success:
            if invalid:
                try:
                    self.__invalid_users[user] += 1
                except:
                    self.__invalid_users[user] = 1
                
            else:
                try:
                    self.__valid_users[user] += 1
                except:
                    self.__valid_users[user] = 1
                    
                try:
                    self.__valid_users_and_hosts[user_host_key] += 1
                except:
                    self.__valid_users_and_hosts[user_host_key] = 1


            try:
                self.__abusive_hosts[host] += 1
            except:
                self.__abusive_hosts[host] = 1
                

    def get_abusive_hosts(self):
        return self.__get_stats(ABUSIVE_HOSTS)

    def get_abused_users_invalid(self):
        return self.__get_stats(ABUSED_USERS_INVALID)

    def get_abused_users_valid(self):
        return self.__get_stats(ABUSED_USERS_VALID)

    def get_abused_users_and_hosts(self):
        return self.__get_stats(ABUSED_USERS_AND_HOSTS)

    def get_suspicious_logins(self):
        return self.__get_stats(SUSPICIOUS_LOGINS)


    def __get_stats(self, fname):
        path = os.path.join(self.__work_dir, fname)
        stats = {}
        try:
            for line in open(path, "r"):
                try:
                    name, value = line.split(":")
                    stats[name] = int(value)
                except:
                    pass                
        except Exception, e:
            if not self.__first_time: print e
            
        return stats


    def save_all_stats(self):
        self.save_abusive_hosts()
        self.save_abused_users_valid()
        self.save_abused_users_invalid()
        self.save_abused_users_and_hosts()
        self.save_suspicious_logins()

    def save_abusive_hosts(self):
        self.__save_stats(ABUSIVE_HOSTS, self.__abusive_hosts)

    def save_abused_users_invalid(self):
        self.__save_stats(ABUSED_USERS_INVALID, self.__invalid_users)

    def save_abused_users_valid(self):
        self.__save_stats(ABUSED_USERS_VALID, self.__valid_users)

    def save_abused_users_and_hosts(self):
        self.__save_stats(ABUSED_USERS_AND_HOSTS, self.__valid_users_and_hosts)

    def save_suspicious_logins(self):
        self.__save_stats(SUSPICIOUS_LOGINS, self.__suspicious_logins)
        

    def get_deny_hosts(self, threshold):
        hosts = self.__abusive_hosts.keys()
        deny_hosts = [host for host,num in self.__abusive_hosts.items()
                      if num > threshold]

        return deny_hosts
        

    def __save_stats(self, fname, stats):
        path = os.path.join(self.__work_dir, fname)
        try:
            fp = open(path, "w")
        except Exception, e:
            print e
            return

        
        keys = stats.keys()
        keys.sort()

        for key in keys:
            fp.write("%s:%d\n" % (key, stats[key]))
        fp.close()
        

#################################################################################

class AllowedHosts:
    def __init__(self, work_dir):
        self.allowed_path = os.path.join(work_dir, ALLOWED_HOSTS)
        self.allowed_hosts = {}
        self.load_hosts()

    def __contains__(self, ip_addr):
        if self.allowed_hosts.has_key(ip_addr): return 1
        else: return 0

    def dump(self):
        print "Dumping AllowedHosts"
        print self.allowed_hosts.keys()

        
    def load_hosts(self):
        try:
            fp = open(self.allowed_path, "r")
        except:
            return

        for line in fp:
            line = line.strip()
            if not line or line[0] == '#': continue

            m = ALLOWED_REGEX.match(line)
            if m:
                first3 = m.group('first_3bits')
                fourth = m.group('fourth')
                wildcard = m.group('ip_wildcard')
                ip_range = m.group('ip_range')

                if fourth:
                    self.allowed_hosts["%s%s" % (first3, fourth)] = 1
                elif wildcard:
                    for i in range(256):
                        self.allowed_hosts["%s%s" % (first3, i)] = 1
                else:
                    start, end = ip_range.split("-")
                    for i in range(int(start), int(end)):
                        self.allowed_hosts["%s%d" % (first3, i)] = 1
            
        fp.close()

    
#################################################################################

    
class DenyHosts:
    def __init__(self, logfile, prefs, ignore_offset=0,
                 first_time=0, noemail=0, verbose=0):
        self.__denied_hosts = {}
        self.__prefs = prefs
        self.__first_time = first_time
        self.__noemail = noemail
        self.__verbose = verbose

        file_tracker = FileTracker(self.__prefs.get('WORK_DIR'),
                                   logfile)

        self.__allowed_hosts = AllowedHosts(self.__prefs.get('WORK_DIR'))
                
        if ignore_offset:
            last_offset = 0
        else:
            last_offset = file_tracker.get_offset()

        if last_offset != None:
            self.get_denied_hosts()
            if self.__verbose or DEBUG:
                print "Processing log file (%s) from offset (%ld)" % (logfile,
                                                                      last_offset)
            offset = self.process_log(logfile, last_offset)
            if offset != last_offset:
                file_tracker.save_offset(offset)
        else:
            if self.__verbose or DEBUG:
                print "Log file size has not changed.  Nothing to do."
                


    def get_denied_hosts(self):
        for line in open(self.__prefs.get('HOSTS_DENY'), "r"):
            if line[0] not in ('#', '\n'):
                try:
                    blah, host = line.split(":")
                    host = string.strip(host)
                    self.__denied_hosts[host] = 0
                except:
                    pass


    def update_hosts_deny(self, deny_hosts):
        if not deny_hosts: return None, None

        #print self.__denied_hosts.keys()
        new_hosts = [host for host in deny_hosts
                     if not self.__denied_hosts.has_key(host)
                     and host not in self.__allowed_hosts]
        #print new_hosts

        try:
            fp = open(self.__prefs.get('HOSTS_DENY'), "a")
            status = 1
        except Exception, e:
            print e
            print "These hosts should be manually added to",
            print self.__prefs.get('HOSTS_DENY')
            fp = sys.stdout
            status = 0
            
        for host in new_hosts:
            fp.write("%s: %s\n" % (self.__prefs.get('BLOCK_SERVICE'), host))

        if fp != sys.stdout:
            fp.close()

        return new_hosts, status
    


    def process_log(self, logfile, offset):
        try:
            fp = open(logfile, "r")
        except Exception, e:
            print "Could not open log file: %s" % logfile
            print e
            return -1

        try:
            fp.seek(offset)
        except:
            pass

        
        login_attempt = LoginAttempt(self.__prefs.get('WORK_DIR'),
                                     self.__prefs.get('DENY_THRESHOLD'),
                                     self.__first_time)

        for line in fp:
            success = invalid = 0
            m = FAILED_ENTRY_REGEX.match(line)
            if m:
                if m.group("invalid"): invalid = 1
            else:
                m = SUCCESSFUL_ENTRY_REGEX.match(line)
                if m:
                    success = 1
            if not m:
                continue
            
            if m:               
                user = m.group("user")
                host = m.group("host")

                login_attempt.add(user, host, success, invalid)
                    

        offset = fp.tell()
        fp.close()

        login_attempt.save_all_stats()
        deny_hosts = login_attempt.get_deny_hosts(self.__prefs.get('DENY_THRESHOLD'))

        #print deny_hosts
        new_denied_hosts, status = self.update_hosts_deny(deny_hosts)
        new_suspicious_logins = login_attempt.get_new_suspicious_logins()

        if self.__verbose or DEBUG:
            print "new denied hosts:", str(new_denied_hosts)
            print "new sucpicious logins:", str(new_suspicious_logins)

        if not noemail and new_denied_hosts or new_suspicious_logins:
            send_email(self.__prefs, new_denied_hosts, status, new_suspicious_logins)
            
        return offset

#################################################################################

    
if __name__ == '__main__':
    logfiles = []
    config_file = CONFIG_FILE
    ignore_offset = 0
    noemail = 0
    verbose = 0
    args = sys.argv[1:]
    try:
        (opts, getopts) = getopt.getopt(args, 'f:c:dinv?hV',
                                        ["=file", "ignore", "verbose", "debug",
                                         "help", "noemail", "=config"])
    except:
        print "\nInvalid command line option detected."
        usage()
        sys.exit(1)

    for opt, arg in opts:
        if opt in ('-h', '-?', '--help'):
            usage()
            sys.exit(0)
        if opt in ('-f', '--file'):
            logfiles.append(arg)
        if opt in ('-i', '--ignore'):
            ignore_offset = 1
        if opt in ('-n', '--noemail'):
            noemail = 1
        if opt in ('-v', '--verbose'):
            verbose = 1
            first_time = 0
        if opt in ('-d', '--debug'):
            DEBUG = 1            
        if opt in ('-c', '--config'):
            config_file = arg

    prefs = Prefs(config_file)
    first_time = 0
    try:
        os.makedirs(prefs.get('WORK_DIR'))
        first_time = 1
    except Exception, e:
        if e[0] != 17:
            print e
            sys.exit(1)

    if DEBUG:
        print "Debug mode enabled."
        prefs.dump()
    
    if not logfiles:
        logfiles = [prefs.get('SECURE_LOG')]
    elif len(logfiles) > 1:
        ignore_offset = 1

    if not prefs.get('ADMIN_EMAIL'): noemail = 1


    for f in logfiles:
        dh = DenyHosts(f, prefs, ignore_offset, first_time, noemail, verbose)
                

            