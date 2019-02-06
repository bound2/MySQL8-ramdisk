from subprocess import call
from subprocess import Popen
from subprocess import PIPE
import ConfigParser
import abc
import argparse


class Ramdisk(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def start_ramdisk(self, ramdisk_name, ramdisk_size_mb):
        """Create ramdisk on the operating system"""
        raise NotImplementedError

    @abc.abstractmethod
    def ramdisk_dir(self, ramdisk_name):
        """Return a path to system ramdisk"""
        raise NotImplementedError

    @abc.abstractmethod
    def shutdown_ramdisk(self, ramdisk_dir):
        """Shutdown ramdisk that was created on the operating system"""
        raise NotImplementedError

    @abc.abstractmethod
    def start_mysql(self, ramdisk_dir, mysql_dir, mysql_user, mysql_hostname, mysql_password, mysql_auth_plugin, mysql_default_collation, executable_sqls):
        """Start MySQL on the ramdisk and execute provided sqls"""
        raise NotImplementedError

    @abc.abstractmethod
    def shutdown_mysql(self, mysql_dir, mysql_user, mysql_password):
        """Shutdown MySQL that was started on ramdisk"""
        raise NotImplementedError


class MacRamdisk(Ramdisk):

    def start_ramdisk(self, ramdisk_name, ramdisk_size_mb):
        size = ramdisk_size_mb * 2048
        start_ramdisk_command = 'diskutil erasevolume HFS+ "%s" `hdiutil attach -nomount ram://%s`' % (ramdisk_name, size)
        call(start_ramdisk_command, shell=True)

    def ramdisk_dir(self, ramdisk_name):
        ramdisk_dir = '/Volumes/%s' % (ramdisk_name)
        return ramdisk_dir

    def shutdown_mysql(self, mysql_dir, mysql_user, mysql_password):
        shutdown_mysql_command = '%s/bin/mysqladmin -u%s -p%s shutdown' % (mysql_dir, mysql_user, mysql_password)
        call(shutdown_mysql_command, shell=True)

    def shutdown_ramdisk(self, ramdisk_dir):
        shutdown_ramdisk_command = 'diskutil unmount %s' % (ramdisk_dir)
        call(shutdown_ramdisk_command, shell=True)

    def _reset_mysql_password(self, mysql_user, mysql_hostname, mysql_passwor, mysql_auth_plugin):
        mysql_command = 'mysql -u%s -e "ALTER USER \'%s\'@\'%s\' IDENTIFIED WITH %s BY \'%s\' "' % (mysql_user, mysql_user, mysql_hostname, mysql_auth_plugin, mysql_password)
        call(mysql_command, shell=True)

    def start_mysql(self, ramdisk_dir, mysql_dir, mysql_user, mysql_hostname, mysql_password, mysql_auth_plugin, mysql_default_collation, executable_sqls):
        copy_mysql_command = '%s/bin/mysqld --initialize-insecure --basedir=%s --datadir=%s' % (mysql_dir, mysql_dir, ramdisk_dir)
        call(copy_mysql_command, shell=True)

        start_command = '%s/bin/mysql.server start' % (mysql_dir)
        call(start_command, shell=True)

        self._validate_datadir(mysql_user, ramdisk_dir)
        self._validate_basedir(mysql_user, mysql_dir)
        
        collation_command = 'mysql -u%s -e "SET PERSIST default_collation_for_utf8mb4=%s"' % (mysql_user, mysql_default_collation)
        call(collation_command, shell=True)

        for sql in executable_sqls:
            mysql_command = 'mysql -u%s -e "%s"' % (mysql_user, sql.replace('`', '\`'))
            call(mysql_command, shell=True)

        self._reset_mysql_password(mysql_user, mysql_hostname, mysql_password, mysql_auth_plugin)

    def _validate_datadir(self, mysql_user, ramdisk_dir):
        process = Popen(['mysql', "-u" + mysql_user, "-e", 'SELECT @@datadir'], stdout=PIPE)
        while True:
            result = process.stdout.readline().rstrip()
            if result != '':
                if ramdisk_dir in result:
                    return True
            else:
                break

        print "Consider adding datadir=%s to your my.cnf and restart ramdisk, otherwise mysql ramdisk might not work" % (ramdisk_dir)
        return False

    def _validate_basedir(self, mysql_user, mysql_dir):
        process = Popen(['mysql', "-u" + mysql_user, "-e", 'SELECT @@basedir'], stdout=PIPE)
        while True:
            result = process.stdout.readline().rstrip()
            if result != '':
                if mysql_dir in result:
                    return True
            else:
                break

        print "Consider adding basedir=%s to your my.cnf and restart ramdisk, otherwise mysql ramdisk might not work" % (mysql_dir)
        return False

if __name__ == '__main__':

    arg_parser = argparse.ArgumentParser(description='')
    arg_parser.add_argument('--stop', action='store_true', help='shutdown ramdisk and MySQL')
    args = arg_parser.parse_args()

    config = ConfigParser.ConfigParser(allow_no_value=True)
    config.read('config.ini')

    mysql_config = dict(config.items('mysql'))

    mysql_user = mysql_config.get('user')
    mysql_hostname = mysql_config.get('hostname')
    mysql_dir = mysql_config.get('directory')
    mysql_password = mysql_config.get('password')
    mysql_auth_plugin = mysql_config.get('auth_plugin')
    mysql_default_collation = mysql_config.get('default_collation_for_utf8mb4')

    ramdisk_config = dict(config.items('ramdisk'))
    ramdisk_name = ramdisk_config.get('name')
    ramdisk_size_mb = int(ramdisk_config.get('size_mb'))

    parsed_sqls = config.options('executablesql')
    executable_sqls = list()

    for sql in parsed_sqls:
        if len(sql) > 0:
            executable_sqls.append(sql)

    ramdisk = MacRamdisk()
    ramdisk_dir = ramdisk.ramdisk_dir(ramdisk_name)
    if not args.stop:
        ramdisk.start_ramdisk(ramdisk_name, ramdisk_size_mb)
        ramdisk.start_mysql(ramdisk_dir, mysql_dir, mysql_user, mysql_hostname, mysql_password, mysql_auth_plugin, mysql_default_collation, executable_sqls)
    else:
        ramdisk.shutdown_mysql(mysql_dir, mysql_user, mysql_password)
        ramdisk.shutdown_ramdisk(ramdisk_dir)
