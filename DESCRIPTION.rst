Python LiveJournal
==================

**Feel free to make pull requests!**

| **A python realization of LiveJournal (LJ) API**
| A full description of the protocol can be found at:
| http://www.livejournal.com/doc/server/ljp.csp.xml-rpc.protocol.html

Installation
------------

Just type (pip integration is work in progress):

.. code:: bash

    pip install lj

You can also find `Python LJ on Github
<https://github.com/daniilr/python-lj/>`_

Usage example
-------------

.. code:: python

    from lj import lj as _lj
    lj = _lj.LJServer("Python-Blog3/1.0", "http://daniil-r.ru/bots.html; i@daniil-r.ru")
    lj.login("yourusername", "yourpassword")
    lj.postevent("Awesome post", "Awesome subject", props={"taglist": "github,livejournal"})
