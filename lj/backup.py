#!/usr/bin/env python3

__revision__ = "$Rev$"
try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import pickle
import datetime
import time
import os.path
import sys
from optparse import OptionParser
import lj


"""
journal backup dictionary structure:
    { 'last_entry': timestamp of the last journal entry sync'd,
      'last_comment': id of the last comment sync'd,
      'login': the dictionary returned by the last login (useful information such as friend groups),
      'comment_posters': { [posterid]: [postername] }
      'entries': { [entryid]: {
          eventtime: timestamp,
          security: 'private' or 'usemask',
          allowmask: bitmask of usergroups allowed to see post,
          subject: subject,
          event: event text (url-encoded),
          poster: user who posted the entry (if different from logged-in user),
          props: dictionary of properties,
          [other undocumented keys returned in a pseudo-arbitrary fashion by LJ],
      } }
      comments: { [commentid]: {
          'posterid': poster id (map to username with comment_posters),
          'jitemid': entry id,
          'parentid': id of parent comment (0 if top-level),
          'body': text of comment,
          'date': date comment posted,
          'subject': subject of comment,
          [other undocumented keys returned in a pseudo-aritrary fashion by LJ],
      } }
    }
"""

DEFAULT_JOURNAL = {
    'last_entry': None,
    'last_comment': '0',
    'last_comment_meta': None,
    'entries': {},
    'comments': {},
    'comment_posters': {},
}


def datetime_from_string(s):
    """This assumes input in the form '2007-11-19 12:24:01' because that's all I care about"""
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def days_ago(s):
    return (datetime.datetime.today() - datetime_from_string(s)).days


def one_second_before(s):
    return str(datetime_from_string(s) - datetime.timedelta(seconds=1))


def backup(user, password, journal):
    server = lj.LJServer('lj.py+backup; kemayo@gmail.com', 'Python-lj.py/0.0.1')
    try:
        login = server.login(user, password, getpickws=True, getpickwurls=True)
    except lj.LJException as e:
        sys.exit(e)

    # Load already-cached entries

    journal['login'] = login

    # Sync entries from the server
    print("Downloading journal entries")
    nj = update_journal_entries(server, journal)

    # Sync comments from the server
    print("Downloading comments")
    nc = update_journal_comments(server, journal)

    print(("Updated %d entries and %d comments" % (nj, nc)))


def backup_to_file(user, password, f):
    journal = load_journal(f)
    backup(user, password, journal)
    save_journal(f, journal)


def load_journal(f):
    # f should be a string referring to a file
    if os.path.exists(f):
        try:
            j = pickle.load(open(f, 'rb'))
            return j
        except EOFError:
            return DEFAULT_JOURNAL.copy()
    return DEFAULT_JOURNAL.copy()


def save_journal(f, journal):
    pickle.dump(journal, open(f, 'wb'))


def update_journal_entries(server, journal):
    syncitems = built_syncitems_list(server, journal)
    howmany = len(syncitems)
    print(howmany, "entries to download")
    while len(syncitems) > 0:
        print("getting entries starting at", syncitems[0][1])
        sync = server.getevents_syncitems(one_second_before(syncitems[0][1]))
        for entry in sync['events']:
            if hasattr(entry, 'data'):
                entry = entry.data
            journal['entries'][entry['itemid']] = entry
            del(syncitems[0])
    return howmany


def built_syncitems_list(server, journal):
    all = []
    count = 0
    total = None
    while count != total:
        sync = server.syncitems(journal.get('last_entry'))
        count = sync['count']
        total = sync['total']
        journalitems = [(int(e['item'][2:]), e['time']) for e in sync['syncitems'] if e['item'].startswith('L-')]
        if journalitems:
            all.extend(journalitems)
            journal['last_entry'] = all[-1][1]
    return all


def update_journal_comments(server, journal):
    session = server.sessiongenerate()
    initial_meta = get_meta_since(journal['last_comment'], server, session)
    journal['comment_posters'].update(initial_meta['usermaps'])
    if initial_meta['maxid'] > journal['last_comment']:
        bodies = get_bodies_since(journal['last_comment'], initial_meta['maxid'], server, session)
        journal['comments'].update(bodies)
    if len(journal['comments']) == 0 or days_ago(journal['last_comment_meta']) > 30:
        # update metadata every 30 days
        all_meta = get_meta_since('0', server, session)
        journal['comment_posters'].update(all_meta['usermaps'])
        if len(journal['comments']) > 0:
            for id, data in list(all_meta['comments'].items()):
                journal['comments'][id]['posterid'] = data[0]
                journal['comments'][id]['state'] = data[1]
        journal['last_comment_meta'] = str(datetime.datetime.today())
    howmany = int(initial_meta['maxid']) - int(journal['last_comment'])
    journal['last_comment'] = initial_meta['maxid']
    server.sessionexpire(session)
    return howmany


def get_meta_since(highest, server, session):
    all = {'comments': {}, 'usermaps': {}}
    maxid = str(int(highest) + 1)
    while highest < maxid:
        meta = server.fetch_comment_meta(highest, session)
        maxid = meta['maxid']
        for id, data in list(meta['comments'].items()):
            if int(id) > int(highest):
                highest = id
            all['comments'][id] = data
        all['usermaps'].update(meta['usermaps'])
    all['maxid'] = maxid
    return all


def get_bodies_since(highest, maxid, server, session):
    all = {}
    while highest != maxid:
        meta = server.fetch_comment_bodies(highest, session)
        for id, data in list(meta.items()):
            if int(id) > int(highest):
                highest = id
            all[id] = data
        if maxid in meta:
            break
        print("Downloaded %d comments so far" % len(all))
    return all


def __dispatch():
    parser = OptionParser(version="%%prog %s" % __revision__, usage="usage: %prog -u Username -p Password -f backup.pkl")
    parser.add_option('-u', dest='user', help="Username")
    parser.add_option('-p', dest='password', help="Password")
    parser.add_option('-f', dest='file', help="Backup filename")
    parser.add_option('-c', dest='config', help="Config file")

    options, args = parser.parse_args(sys.argv[1:])
    if options.config:
        cp = configparser.ConfigParser()
        cp.read(options.config)
        username = cp.get("login", "username")
        password = cp.get("login", "password")
        filename = cp.get("login", "file")
        backup_to_file(username, password, filename)
    elif options.user and options.password and options.file:
        backup_to_file(options.user, options.password, options.file)
    else:
        parser.error("If a config file is not being used, -u, -p, and -f must all be present.")

if __name__ == "__main__":
    __dispatch()
