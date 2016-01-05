![Format](https://img.shields.io/pypi/format/lj.svg)
![Versions](https://img.shields.io/pypi/pyversions/lj.svg)
![Versions](https://img.shields.io/pypi/dm/lj.svg)

# Python LiveJournal #
**Feel free to make pull requests!**

**A python realization of LiveJournal (LJ) API**
A full description of the protocol can be found at: 
http://www.livejournal.com/doc/server/ljp.csp.xml-rpc.protocol.html

## Installation ##
Just type (pip integration is work in progress):
```bash
pip install lj
```
## Usage example ##

```python
from lj import lj
ljclient = lj.LJServer("Python-Blog3/1.0", "http://daniil-r.ru/bots.html; i@daniil-r.ru")
ljclient.login("yourusername", "yourpassword")
ljclient.postevent("Awesome post", "Awesome subject", props={"taglist": "github,livejournal"})
```
