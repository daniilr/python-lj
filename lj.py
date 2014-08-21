"""LiveJournal interface module

Implements the LiveJournal xmlrpc client protocol.

Todo:
 * Support for adding a fastserver cookie to the request (subclass xmlrpc.Transport to pass to the ServerProxy)
 * Centralise validation code.  Elegantly.

A full description of the protocol can be found at: http://www.livejournal.com/doc/server/ljp.csp.xml-rpc.protocol.html
"""

__author__ = "David Lynch (kemayo@gmail.com)"
__version__ = "$Revision$"
__date__ = "$Date: 2004/11/30 10:43:00 PST $"
__copyright__ = "Copyright (c) 2004-2007 David Lynch"
__license__ = "New BSD"

from hashlib import md5
import xmlrpclib
import urllib2
import StringIO
import gzip
import datetime
from xml.dom.minidom import parse


class LJException(Exception):
    pass


class LJTransport(xmlrpclib.Transport):
    pass


class LJServer:

    """Main interface class for interactions with servers implementing the LiveJournal XML-RPC interface

    clientversion:  the identifier of the client.  This should be a string of the form
        Platform-ProductName/ClientVersionMajor.Minor.Rev. (e.g. 'Python-PyLJ/1.0.3')
    user_agent:  the user agent for this client.  This should be a string of the form
        "http://example.com/ljtoy.html; bob@example.com", per the LJ Bot Policy.
    host: server to connect to.  Defaults to the official LiveJournal server.  Note that
        it is assumed everything on this server is in the same location as it is on
        livejournal.com.

    All data transmitted should be in UTF-8.  All data received WILL be in UTF-8.
    """

    def __init__(self, clientversion, user_agent, host='http://www.livejournal.com/'):
        transport = LJTransport()
        transport.user_agent = user_agent
        self.user_agent = user_agent
        self.host = host
        self.server = xmlrpclib.ServerProxy(
            host + 'interface/xmlrpc', transport)
        self.clientversion = clientversion

        self.user = None
        self.password = None
        self.lastupdate = None
        self.valid = {}

    def __request(self, methodname, args):
        """__request(methodname, arguments)
        Internal function that submits a request to the LiveJournal server.
        methodname is the name of the XMLRPC method to call
        args is a dictionary of arguments to pass to that method
        """
        method = getattr(self.server.LJ.XMLRPC, methodname)

        response = method(args)
        return response

    def __loggedin(self):
        if self.user is None or self.password is None:
            raise LJException('Must be logged in to access LiveJournal')

    def __headers(self):
        self.__loggedin()
        challenge = self.getchallenge()
        args = {'ver': 1,
                'clientversion': self.clientversion,
                'auth_method': 'challenge',
                'auth_challenge': challenge['challenge'],
                'auth_response': md5(challenge['challenge'] + md5(self.password).hexdigest()).hexdigest(),
                'username': self.user,
                }
        return args

    def login(self, user, password, getmoods=None, getmenus=None, getpickws=None, getpickwurls=None):
        """Logs into the LJ server.
        Requires username and password.
        Optional arguments are:
            getmoods - send the id of the highest mood the client has cached (LJ *really* wants
                you to cache this.
            getmenus - send something (they don't care what)
            getpickws - send something
            getpickwurls - send something, must have set getpickws
        This is the gateway function -- it sets up username and password, validates them with the
        server, then sets internal variables up for other functions in this class.  None of the
        other functions in this class will work until login has run.
        If login succeeds, a dictionary is returned.  This contains the following keys:
            'friendgroups': list of dictionaries.  Each dictionary represents a friend group as follows:
                'public': int (0 or 1)
                'sortorder': int
                'name': string
                'id': int
            'fullname': string
            'userid': int (not actually used in any requests -- but it makes a handy unique identifier
                for client-side data)
            'usejournals': list of the journal names the user is allowed to use
        If you gave optional arguments LJ will add extra keys to the dictionary as follows (it's fairly
        obvious which argument causes which key to appear...):
            'fastserver': int (1), only appears if the user is a paid user
            'moods': list of dictionaries.  Each dictionary represents a mood as follows:
                'id': int
                'parent': int - maps to id in a many-to-one relationship.  Used for inhereiting mood icons.
                'name': string
            'pickws': list of the picture keywords.  Note:
                "The client should also do a case-insensitive compare on this list when a mood is selected
                or entered, and auto-select the current picture keyword. That way it seems that selecting
                a mood also sets their corresponding picture."
            'pickwurls': list of picture urls.  (In same order as pickws)
            'defaultpicurl': string - url of the default picture (used if you don't supply a keyword when
                posting)
            'menus': list of dictionaries representing a menu that can be provided in the client for links
                to livejournal, as follows:
                'text': string - can be '-' to represent a separator in the menu
                'url': string - is '' if a separator
                'sub': Optional list of dictionaries, same structure as this.  If it's present, the node
                    represents a submenu, and 'url' will be ''.
        If login fails, it raises an LJException passing through whatever error message LiveJournal
        gave it.
        The class appropriates a few bits of this data for use in validating input to other methods.  Because
        of this if any changes are made to data on LJ servers (e.g. adding posting access to other journals,
        or changing userpic keywords) via another client or the web interface, they won't affect the class
        until login is run again.
        """
        if self.valid:
            self.valid = {}
        self.user = user
        self.password = password
        arguments = self.__headers()
        if getmoods:
            arguments['getmoods'] = getmoods
        if getmenus:
            arguments['getmenus'] = getmenus
        if getpickws:
            arguments['getpickws'] = getpickws
        if getpickwurls:
            arguments['getpickwurls'] = getpickwurls

        try:
            response = self.__request('login', arguments)
        except xmlrpclib.Error, v:
            self.user = None
            self.password = None
            raise LJException(v)
        if 'usejournals' in response:
            self.valid['usejournals'] = response['usejournals']
        if 'pickws' in response:
            self.valid['pickws'] = response['pickws']
        return response

    def checkfriends(self, mask=None):
        """Check for friend updates
        One optional arguments:
        mask - the id of the friend group to check, defaults to all friends
        Returns a dictionary containing the following keys:
            'lastupdate': string - date of the last friends page update
            'interval': int - how long you should wait before polling checkfriends again
            'new': int (0 or 1) - whether there are any new entries
            Note that this will always return that there are no new updates the first time it runs, as the
        first run lacks lastupdate info.  If you want to remember lastupdate across sessions, you'll need
        to adjust the self.lastupdate variable.
        """
        arguments = self.__headers()
        if mask:
            arguments['mask'] = mask
        if self.lastupdate is not None:
            arguments['lastupdate'] = self.lastupdate
        try:
            response = self.__request('checkfriends', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        self.lastupdate = response['lastupdate']
        return response

    def consolecommand(self, commands):
        """Runs a command on the LJ console
        One required argument - 'commands' must be a list of strings
        Returns a dictionary with the key 'results'
        'results' contains a list of dictionaries structured as follows:
            'output': list of lists, each representing a line and containing two strings, the first being
                the type of output.  I think.
            'success': int (1 or 0)
        """
        arguments = self.__headers()
        arguments['commands'] = commands
        try:
            response = self.__request('consolecommand', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response

    def editevent(self, itemid, event, subject=None, e_datetime=None, security=None, allowmask=None, props=None, usejournal=None, lineendings=None):
        pass

    def editfriendgroups(self, groupmasks, set=None, delete=None):
        pass

    def editfriends(self, friends, delete=None, add=None):
        """Add or delete friends.
        Takes one required argument: 'friends', a list of lists or strings
        Each inner list should be structured like so:
            ['username','fgcolor','bgcolor','groupmask']
        Only 'username' is required. 'fgcolor' defaults to '#000000', 'bgcolor' defaults to '#ffffff',
            'groupmask' defaults to none, which means the new friend belongs to no groups.
        Only use groupmask if the friendgroups list has been *very* recently updated.
        Depending on the value of 'delete' and 'add', you will either remove or add the users to the friendslist.
        If 'delete', 'friends' must be a list of strings; if 'add', it must be a list of lists.
        Returns a dictionary with the following structure:
            'added': list of ['username','fullname']
        Returns an empty dictionary if users were removed.
        """
        arguments = self.__headers()
        if add:
            arguments['add'] = friends
        elif delete:
            arguments['delete'] = friends
        try:
            response = self.__request('editfriends', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response

    def friendof(self, limit=None):
        """Fetches a list of users who list the logged in user as their friend
        Optional argument 'limit' -> int (number of items to return)
        Returns dictionary with the following structure:
            'friendofs': list of dictionaries as follows,
                'username': username
                'fullname': full name
                'bgcolor': background color
                'fgcolor': foreground color
        """
        arguments = self.__headers()
        if limit:
            arguments['friendoflimit'] = limit
        try:
            response = self.__request('friendof', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response

    def getchallenge(self):
        """Fetches a challenge for auth_challenge
        No arguments.
        I don't know of anything that you'd want to do with a challenge that isn't covered by the other
        functions in this class  -- it's only used for authenticating when sending a command to the
        server.  But for the sake of having every protocol method available, here it is.
        This is the only function that will work prior to login
        Returns a dictionary with the following keys:
            'auth_scheme': string - currently not used for anything, and is always 'c0'.  In the future,
                if LJ implements other auth schemes, this would be the basis of negotiating with the server
                which of the schemes the client understands is best.
            'challenge': string - single-use opaque cookie used to generate a password hash
            'expire_time': int - unix time on lj servers when the challenge will expire
            'server_time': int - current unix time on lj servers (expire_time - server_time = challenge lifetime)
        """
        return self.__request('getchallenge', {})

    def getdaycounts(self, usejournal=None):
        """Fetch a list of days and the number of entries made for each.
        Optional argument 'usejournal' is the username of a journal the user has posting access to.
        Returns a dictionary as follows:
            'daycounts': list of dictionaries,
                'date': string (YYYY-MM-DD)
                'count': int (entries that day)
        """
        arguments = self.__headers()
        if usejournal and usejournal in self.valid['usejournals']:
            arguments['usejournal'] = usejournal
        try:
            response = self.__request('getdaycounts', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response

    def _getevents(self, **kwds):
        """Fetches a number of entries from the server
        Argument combinations are complicated enough that helper methods are defined below.
        These arguments are common to all helpers:
         usejournal - the journal to fetch entries from (only the journals returned in 'usejournals' by login will work)
         lineendings - the line-ending type to use, can be 'unix', 'pc', or 'mac', defaults to 'unix'
         truncate - if >=4 returns the entry text truncated to (truncate-3) in length, plus '...'.
         prefersubject - if true no subjects are returned, the event text is the subject if one exists
         noprops - if true no metadata properties are returned
        Returns: List of dictionaries with keys:
         itemid - integer item id
         eventtime - time the user posted the entry
         security - 'private' or 'usemask'
         allowmask - if security is 'usemask', the 32-bit bitmask of friend groups allowed to view the entry
         subject - entry subject
         event - entry body
         poster - if different than usejournal, user who posted the entry
         props - dict of properties
        """
        arguments = self.__headers()
        arguments.update(**kwds)
        # This if-else section handles the various combinations of selecttype, selectby and seldate
        # if usejournal and usejournal in self.valid['usejournals']:
        # if truncate and truncate > 4:

        try:
            response = self.__request('getevents', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response

    def getevents_one(self, itemid=-1, **kwds):
        """Fetches a single event
        itemid is the id of the event to fetch; it defaults to -1, which means the most recent event
        """
        return self._getevents(selecttype="one", itemid=itemid, **kwds)

    def getevents_lastn(self, n=20, before=None, **kwds):
        """Fetches the last 'n' events before the given date
        n defaults to 20, and can be a max of 50.
        """
        if before and type(before) != str:
            before = before.strftime('%Y-%m-%d %H:%M:%S')
        return self._getevents(selecttype="lastn", howmany=n, beforedate=before, **kwds)

    def getevents_day(self, year=None, month=None, day=None, **kwds):
        """Fetches the events for a particular day
        Defaults to today if year, month, or day are not specified.
        """
        if not (year and month and day):
            today = datetime.date.today()
            year = today.year
            month = today.month
            day = today.day
        return self._getevents(selecttype="day", year=year, month=month, day=day, **kwds)

    def getevents_syncitems(self, lastsync=None, **kwds):
        """Fetches all entries modified or created since lastsync
        This should be used in conjunction with the syncitems api call.
        """
        if lastsync and type(lastsync) != str:
            lastsync = lastsync.strftime('%Y-%m-%d %H:%M:%S')
        return self._getevents(selecttype="syncitems", lastsync=lastsync, **kwds)

    def getfriends(self, friendof=None, groups=None, limit=None):
        arguments = self.__headers()
        if friendof:
            arguments['includefriendof'] = 1
        if groups:
            arguments['includegroups'] = 1
        if limit:
            arguments['friendlimit'] = limit
            if friendof:
                arguments['friendoflimit'] = limit
        try:
            response = self.__request('getfriends', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response

    def getfriendgroups(self):
        arguments = self.__headers()
        try:
            response = self.__request('getfriendgroups', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response

    def postevent(self, event, subject=None, e_datetime=None, props=None, security=None, usejournal=None, lineendings=None):
        """Posts an entry to the server
        Requires:
        event: string - text of the entry
        Optional:
        subject: string, less than 100 characters long
        e_datetime: datetime.datetime - date and time of the event, only read up to the minute
        props: dictionaries, with keys as described in http://www.livejournal.com/doc/server/ljp.csp.proplist.html
        lineendings: string ('unix', 'pc', 'mac') - only necessary if using mac line endings
        security: string ('public', 'private', ''friends') or list of ints - defaults to public
            if security is a list, it represents the friend groups that can see the entry
            list is of the group ids returned during login
            """

        arguments = self.__headers()
        arguments['event'] = event

        if not e_datetime:
            e_datetime = datetime.datetime.now()
        try:
            arguments['year'] = e_datetime.year
            arguments['mon'] = e_datetime.month
            arguments['day'] = e_datetime.day
            arguments['hour'] = e_datetime.hour
            arguments['min'] = e_datetime.minute
        except AttributeError:
            raise TypeError('e_datetime must be datetime.datetime, or similar')

        if subject and len(subject) <= 100:
            arguments['subject'] = subject
        if props:
            # validate this?
            arguments['props'] = props
        if security:
            if security in ('public', 'private'):
                arguments['security'] = security
            elif security == 'friends':
                arguments['security'] == 'usemask'
                arguments['allowmask'] == 1
            else:
                # Check whether it's referencing a valid group?
                arguments['security'] = 'usemask'
                arguments['allowmask'] = 0
                for group in security:
                    arguments['allowmask'] = arguments[
                        'allowmask'] + 2 ** group
        if usejournal and usejournal in self.valid['usejournals']:
            arguments['usejournal'] = usejournal
        if lineendings in ('unix', 'pc', 'mac'):
            arguments['lineendings'] = lineendings
        try:
            response = self.__request('postevent', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
            return response

    def sessiongenerate(self, expiration='short', ipfixed=False):
        """Generates a session cookie to use when directly accessing LJ

        expiration can be "short" or "long"
        ipfixed can be False or anything else.
        returns the session cookie, a string similar to "ws:test:124:zfFG136kSz"
        (The second field is the username, the third is the session id.)
        """
        arguments = self.__headers()
        arguments['expiration'] = expiration
        if ipfixed:
            arguments['ipfixed'] = 1
        try:
            response = self.__request('sessiongenerate', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response['ljsession']

    def sessionexpire(self, expire):
        """Expires previously generated sessions

        expire can be "all" or a list of session ids

        returns True
        """
        arguments = self.__headers()
        if expire == 'all':
            arguments['expireall'] = 1
        else:
            if type(expire) == str:
                expire = [expire, ]
            arguments['expire'] = expire
        try:
            response = self.__request('sessionexpire', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return True

    def syncitems(self, lastsync=None):
        """Fetches a list of items to synchronise with a local cache

        optional argument lastsync can be a date in the form "2002-07-13 00:00:00";
            don't generate this locally, just pass the cached date from a previous syncitems call

        returns a dictionary containing the following keys:
         syncitems - a list of dictionaries, each containing:
          item - item id, in the form "Type-Number", where type could potentially
                 be lots of things, but for now will just be "L" for "log entry"
          action - 'create' or 'update'
          time - Server time at which action occurred; to be cached for use as the lastsync argument
         count - number of items contained in this response
         total - total number of items to sync since lastsync
        note that this just returns item ids, not the items; use getevents to get the items
        if total > count you'll need to call syncitems again to complete the sync
        """
        arguments = self.__headers()
        if lastsync:
            arguments['lastsync'] = lastsync
        try:
            response = self.__request('syncitems', arguments)
        except xmlrpclib.Error, v:
            response = None
            raise LJException(v)
        return response

    def __request_with_cookie(self, url, session=None):
        if not session:
            session = self.sessiongenerate()

        request = urllib2.Request(url)
        request.add_header('Accept-encoding', 'gzip')
        request.add_header('User-agent', self.user_agent)
        request.add_header('Cookie', 'ljsession='+session)
        response = urllib2.urlopen(request)
        data = StringIO.StringIO(response.read())
        response.close()
        if response.headers.get('content-encoding', '') == 'gzip':
            data = gzip.GzipFile(fileobj=data)
        return data

    def fetch_comment_meta(self, startid=0, session=None):
        """Fetch comment metadata

        Warning: This isn't part of the XMLRPC API, and might possibly change independently of that API.

        arguments:
         startid - The first comment to fetch data for
         session - A session cookie, if you've already generated one (if not, one will be generated for you)

        returns a dictionary with these keys:
         maxid - The highest comment id; if this is higher than the largest comment id whose
            data was returned, call this again
         comments - A dictionary whose keys are comment ids, and whose values are tuples in
            the form (posterid, state):
          posterid - The poster id; can only change from 0 to some non-zero number (maps to entries in usermaps)
          state - Can be:
           'S' = screened
           'D' = deleted
           'A' = active
         usermaps - A dictionary whose keys are posterids, and whose values are usernames

        LJ encourages you to cache this data, but it can change occasionally.
        """
        response = self.__request_with_cookie(self.host+"export_comments.bml?get=comment_meta&startid=%d" % int(startid), session)
        d = parse(response).getElementsByTagName('livejournal')[0]
        response.close()
        data = {'comments': {}, 'usermaps': {}}
        data['maxid'] = get_text_from_single(d, 'maxid')
        for comment in d.getElementsByTagName('comment'):
            state = comment.getAttribute('state')
            if state == u'':
                state = u'A'
            data['comments'][comment.getAttribute('id')] = (comment.getAttribute('posterid'), state)
        for usermap in d.getElementsByTagName('usermap'):
            data['usermaps'][usermap.getAttribute('id')] = usermap.getAttribute('user')
        d.unlink()
        return data

    def fetch_comment_bodies(self, startid=0, session=None):
        """Fetch comment bodies

        Warning: This isn't part of the XMLRPC API, and might possibly change independently of that API.

        arguments:
         startid - The first comment to fetch data for
         session - A session cookie, if you've already generated one (if not, one will be generated for you)

        returns a dictionary whose key is the comment id and whose value is a dictionary in the form:
         posterid - poster id, mapped per usermaps in the metadata
         state - as per state from _meta
         jitemid - journal item id the comment was posted to
         parentid - comment id of the comment this was a reply to; 0 if top-level
         body - the text of the comment
         date - the date the comment was posted, in the form "2004-03-16T19:19:16Z"
         subject - the subject of the comment; may not be present

        The dictionary may contain an arbitrary number of other keys that LJ sees fit to return, such as poster_ip.

        This should be very, very cached.  All information that might change is returned by fetch_comment_meta.
        """
        response = self.__request_with_cookie(self.host+"export_comments.bml?get=comment_body&startid=%d" % int(startid), session)
        d = parse(response).getElementsByTagName('livejournal')[0]
        response.close()
        data = {}
        for comment in d.getElementsByTagName('comment'):
            c = {
                'posterid': comment.getAttribute('posterid'),
                'state': comment.getAttribute('state'),
                'jitemid': comment.getAttribute('jitemid'),
                'parentid': comment.getAttribute('parentid'),
                'body': get_text_from_single(comment, 'body'),
                'subject': get_text_from_single(comment, 'subject'),
                'date': get_text_from_single(comment, 'date'),
            }
            if c['subject'] == u'':
                c['subject'] = u'A'
            data[comment.getAttribute('id')] = c
        d.unlink()
        return data


# Stole this function wholesale from the python.org minidom example.
# The necessity of this function helps explain why I hate the DOM.
def get_text(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc


def get_text_from_single(dom, tag):
    l = dom.getElementsByTagName(tag)
    if l:
        return get_text(l[0].childNodes)
    else:
        return ''

if __name__ == "__main__":
    LJ = LJServer('lj.py; kemayo@gmail.com', 'Python-PyLJ/0.0.1')
    login = LJ.login('test', 'test')
    print login
