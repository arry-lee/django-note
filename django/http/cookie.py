
# 这里是http模块的cookies
from http import cookies

# For backwards compatibility in Django 2.1.
SimpleCookie = cookies.SimpleCookie

# Add support for the SameSite attribute (obsolete when PY37 is unsupported).
cookies.Morsel._reserved.setdefault('samesite', 'SameSite')

# 单条 cookie 是用=分割的键值对
# 多条是用 ; 分割的
# 如 Cookie: sessionid=hwvheujojmcy6zrr7e1cdbn6bl4muewk; csrftoken=taaEIoNODfPXr32U9qUqjLBawWpG8lu7
# 所以 session 是保存在缓存里，浏览器用 cookie 提取这个缓存
def parse_cookie(cookie):
    """
    Return a dictionary parsed from a `Cookie:` header string.
    """
    cookiedict = {}
    for chunk in cookie.split(';'):
        if '=' in chunk:
            key, val = chunk.split('=', 1)
        else:
            # Assume an empty name per
            # https://bugzilla.mozilla.org/show_bug.cgi?id=169091
            key, val = '', chunk
        key, val = key.strip(), val.strip()
        if key or val:
            # unquote using Python's algorithm.
            cookiedict[key] = cookies._unquote(val)
    return cookiedict
