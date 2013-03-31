import os
import subprocess
import ConfigParser
import threading
import Queue
import sqlalchemy
import csv
import time
import glob
import re
import getopt
import sys

def connect(config):
    try:
        ENGINE = config.get('database', 'engine')
        DATABASE = config.get('database', 'database')

        HOST = None if not config.has_option('database', 'host') else config.get('database', 'host')
        USER = None if not config.has_option('database', 'user') else config.get('database', 'user')
        SCHEMA = None if not config.has_option('database', 'schema') else config.get('database', 'schema')
        PASSWORD = None if not config.has_option('database', 'password') else config.get('database', 'password')
    except ConfigParser.NoOptionError:
        print 'Need to define engine, user, password, host, and database parameters'
        raise SystemExit

    if ENGINE == 'sqlite':
        # SQLAlchemy connect string uses a third slash for SQLite
        separator = ':///'

        # SQLite uses a different symbol for bound parameters than MySQL/PostgreSQL
        bound_param = '?'
        dbString = ENGINE + separator + '%s' % (DATABASE)
    else:
        separator = '://'
        bound_param = '%s'

        if USER and PASSWORD:
            # MySQL & PostgreSQL case
            dbString = ENGINE + separator + '%s:%s@%s/%s' % (USER, PASSWORD, HOST, DATABASE)
        else:
            dbString = ENGINE + separator + '%s/%s' % (HOST, DATABASE)
        
    try:
        db = sqlalchemy.create_engine(dbString)
        conn = db.connect()
    except:
        return None
    
    return conn


def parse_rosters(file, conn, bound_param):
    print "processing %s" % file

    reader = csv.reader(open(file))
    for row in reader:
        sql = 'DELETE FROM rosters WHERE player_id = %s AND team_tx = %s'
        conn.execute(sql, [row[0], row[5]])
        
        sql = "INSERT INTO rosters VALUES (%s)" % ", ".join([bound_param] * len(row))
        conn.execute(sql, row)


def parse_teams(file, conn, bound_param):
    print "processing %s" % file

    reader = csv.reader(open(file))
    for row in reader:
        sql = 'DELETE FROM teams WHERE team_id = %s'
        conn.execute(sql, [row[0]])

        sql = "INSERT INTO teams VALUES (%s)" % ", ".join([bound_param] * len(row))
        conn.execute(sql, row)


def parse_games(file, conn, bound_param):
    print "processing %s" % file

    reader = csv.reader(open(file))
    headers = reader.next()
    for row in reader:
        sql = 'DELETE FROM games WHERE game_id = %s'
        conn.execute(sql, [row[0]])

        sql = 'INSERT INTO games(%s) VALUES(%s)' % (','.join(headers), ','.join([bound_param] * len(headers)))
        conn.execute(sql, row)


def parse_events(file, conn, bound_param):
    print "processing %s" % file

    reader = csv.reader(open(file))
    headers = reader.next()
    for row in reader:
        sql = 'DELETE FROM events WHERE game_id = %s AND event_id = %s'
        conn.execute(sql, [row[0], row[96]])

        sql = 'INSERT INTO events(%s) VALUES(%s)' % (','.join(headers), ','.join([bound_param] * len(headers)))
        conn.execute(sql, row)


def main():
    config = ConfigParser.ConfigParser()
    config.readfp(open('config.ini'))
    
    conn = connect(config)
    
    if conn is None:
        print 'Cannot connect to database'
        raise SystemExit
    
    useyear     = False
    verbose     = config.get('debug', 'verbose')
    chadwick    = config.get('chadwick', 'directory')
    path        = os.path.abspath(config.get('download', 'directory'))
    csvpath     = '%s/csv' % path
    files       = []
    years       = []
    opts, args  = getopt.getopt(sys.argv[1:], "y:")
    bound_param = '?' if config.get('database', 'engine') == 'sqlite' else '%s'
    
    os.chdir(path) # Chadwick seems to need to be in the directory
    
    if not os.path.exists('csv'):
        os.makedirs('csv')

    for file in glob.glob("%s/*.EV*" % path):
        files.append(file)

    if len(opts) > 0:
        for o, a in opts:
            if o == '-y':
                yearfile = '%s/%s*.EV*' % (path, a)
                if len(glob.glob(yearfile)) > 0 and a not in years:
                    years.append(int(a))
                    useyear = True
    else:
        for file in files:
            year = re.search(r"^\d{4}", os.path.basename(file)).group(0)
            if year not in years:
                years.append(int(year))

    for year in years:
        if not os.path.isfile('%s/events-%d.csv' % (csvpath, year)):
            cmd = "%s/cwevent -q -n -f 0-96 -x 0-60 -y %d %d*.EV* > %s/events-%d.csv" % (chadwick, year, year, csvpath, year)
            if(verbose):
                print "calling '" + cmd + "'"
            subprocess.call(cmd, shell=True)

        if not os.path.isfile('%s/games-%d.csv' % (csvpath, year)):
            cmd = "%s/cwgame -q -n -f 0-83 -y %d %d*.EV* > %s/games-%d.csv" % (chadwick, year, year, csvpath, year)
            if(verbose):
                print "calling '" + cmd + "'"
            subprocess.call(cmd, shell=True)

    mask = "TEAM*" if not useyear else "TEAM%s*" % years[0]
    for file in glob.glob(mask):
        parse_teams(file, conn, bound_param)

    mask = "*.ROS" if not useyear else "*%s*.ROS" % years[0]
    for file in glob.glob(mask):
        parse_rosters(file, conn, bound_param)

    mask = '%s/games-*.csv' % csvpath if not useyear else '%s/games-%s*.csv' % (csvpath, years[0])
    for file in glob.glob(mask):
        parse_games(file, conn, bound_param)

    mask = '%s/events-*.csv' % csvpath if not useyear else '%s/events-%s*.csv' % (csvpath, years[0])
    for file in glob.glob(mask):
        parse_events(file, conn, bound_param)

    conn.close()


if __name__ == '__main__':
    main()
