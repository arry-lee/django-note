"""
Last-View：2019年8月9日08:51:14
View-Counter：1
"""
from functools import wraps

from django.middleware.cache import CacheMiddleware
from django.utils.cache import add_never_cache_headers, patch_cache_control
from django.utils.decorators import decorator_from_middleware_with_args


def cache_page(timeout, *, cache=None, key_prefix=None):
    """
    用于尝试从缓存中获取页面的视图的装饰器
    如果页面尚未在缓存中，则填充缓存。

    缓存的键 由URL和标头中的一些数据生成。
    此外，还有用于区分不同的键前缀
    缓存多站点设置中的区域。 你可以使用
    get_current_site域，例如，因为它在Django中是唯一的
    项目。

    此外，将采用响应的Vary标头中的所有标头考虑缓存 - 就像中间件一样。
    不同的请求头缓存不一样
    """
    return decorator_from_middleware_with_args(CacheMiddleware)(
        cache_timeout=timeout, cache_alias=cache, key_prefix=key_prefix
    )


# kwargs用于控制缓存行为打补丁一样
def cache_control(**kwargs):
    def _cache_controller(viewfunc):
        @wraps(viewfunc)
        def _cache_controlled(request, *args, **kw):
            response = viewfunc(request, *args, **kw)
            patch_cache_control(response, **kwargs)
            return response
        return _cache_controlled
    return _cache_controller


def never_cache(view_func):
    """
    把响应里加上 never_cache 的响应头
    Decorator that adds headers to a response so that it will never be cached.
    """
    @wraps(view_func)
    def _wrapped_view_func(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response
    return _wrapped_view_func
