
LDAP client
===========

This is the core of the LDAP client from IronPort's code base.

When shrapnel was open-sourced, this was pulled out of a much more
full-featured implementation (but generally not right for this repo).

Also, the asn.1 implementation and surrounding bits have changed quite
a bit since that code was written.

In the ``shrapnel/old/ldap`` directory you can find most of that code,
and if you need something with more features you can probably base your
code on that.  As always, such contributions would be much appreciated.

Example
-------

At the end of ``coro/ldap/client.py`` you'll find a couple of test
functions that show how to use this module.

```python
def t1():
    # sample search
    LOG ('connect...')
    c = client (('127.0.0.1', 389))
    LOG ('bind...')
    c.simple_bind ('', '')
    LOG ('search...')
    r = c.search (
        'dc=ldapserver,dc=example,dc=com',
        SCOPE.SUBTREE,
        DEREF.NEVER,
        0,
        0,
        0,
        '(objectclass=*)',
        []
    )
    LOG ('unbinding...')
    c.unbind()
    from pprint import pprint
    pprint (r)
    coro.set_exit()
    return r
```
	
