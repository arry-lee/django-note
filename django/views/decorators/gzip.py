"""
Last-View：2019年8月9日09:03:46
View-Counter：1
"""
from django.middleware.gzip import GZipMiddleware
from django.utils.decorators import decorator_from_middleware


## @gzip_page 用来压缩视图响应 如果客户端支撑的话
gzip_page = decorator_from_middleware(GZipMiddleware)
gzip_page.__doc__ = "Decorator for views that gzips pages if the client supports it."
