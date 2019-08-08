
# django 源码剖析
django 目录下有以下文件夹：

- apps
	- config.py
	- registry.py
- bin
- conf
- contrib
- core
- db
- dispatch
- forms
- http
- middleware
- template
- templatetags
- test
- urls
- utils
- views

## apps

### apps::config.py 

AppConfig 表示Django应用及其配置类

### apps::registry.py

Apps 存储已安装应用程序配置的注册表

实例化 apps = Apps(installed_apps=None)

### apps::__init__.py

from .config import AppConfig
from .registry import apps

## bin

### bin::django-admin.py

内容如下：

from django.core import management

if __name__ == "__main__":
    management.execute_from_command_line()

## conf

### conf::app_template

包含应用模板文件 .py-tpl;自动生成工程文件时需要。

模板工程包括 __init__|admin|apps|models|tests|views|

### conf::locale

本地化文件,包含各种语言
如中文简体 zh_Hans
其中formats.py 包含了日期数字格式等设置

### conf::project_template

项目模板
- project-template
	- project_name
	 	- __init__.py
	 	- settings.py
	 	- urls.py
	 	- wsgi.py
	manage.py

### conf::urls

处理url的模块

#### conf::urls::__init__.py

#### conf::urls::i18n.py

i18n（其来源是英文单词 internationalization的首末字符i和n，18为中间的字符数）是“国际化”的简称

#### conf::urls::static.py


### conf::__init__.py

先从 DJANGO_SETTINGS_MODULE 环境指定的模块中读取值变量

然后从 django.conf.global_settings.py 读取变量

### conf::global_settings.py

## contrib 
包含一些共享的组件，每个都是独立的，可插拔。稍后学习。

admin|admindocs|auth|contenttypes|flatpages|gis|humanize|messages|postgres|redirects|sessions|sitemaps|sites|staticfiles|syndication

### contrib::admin
后台管理模块

### contrib::admindocs

### contrib::auth
用户认证模块

### contrib::contenttypes

## core
django 核心

### core::cache
缓存

### core::checks
检查
### core::files
文件
### core::handlers
### core::mail
邮箱
### core::management
管理
### core::serializers
序列化 json xml
### core::servers
服务器

### core::exceptions.py
异常
### core::paginator.py
分页器
### core::signals.py
### core::signing.py
### core::validators.py
校验器
### core::wsgi.py


## db 
数据库

### db::backends
### db::migrations
### db::models

## forms
表单
分为 jinja2 和 templates 两类，不知为何

{% include "django/forms/widgets/input.html" %}
### forms::jinja2

### forms::templates

### forms::boundfield.py
### forms::fields.py
### forms::forms.py
### forms::formsets.py
### forms::models.py
### forms::renderers.py
### forms::utils.py
### forms::widgets.py

## http

### http::cookie.py
from django.http.cookie import SimpleCookie, parse_cookie
### http::multipartparser.py

### http::request.py
from django.http.request import (
    HttpRequest, QueryDict, RawPostDataException, UnreadablePostError,
)

### http::response.py
常用
from django.http.response import (
    BadHeaderError, FileResponse, Http404, HttpResponse,
    HttpResponseBadRequest, HttpResponseForbidden, HttpResponseGone,
    HttpResponseNotAllowed, HttpResponseNotFound, HttpResponseNotModified,
    HttpResponsePermanentRedirect, HttpResponseRedirect,
    HttpResponseServerError, JsonResponse, StreamingHttpResponse,
)


__all__ = [
    'SimpleCookie', 'parse_cookie', 'HttpRequest', 'QueryDict',
    'RawPostDataException', 'UnreadablePostError',
    'HttpResponse', 'StreamingHttpResponse', 'HttpResponseRedirect',
    'HttpResponsePermanentRedirect', 'HttpResponseNotModified',
    'HttpResponseBadRequest', 'HttpResponseForbidden', 'HttpResponseNotFound',
    'HttpResponseNotAllowed', 'HttpResponseGone', 'HttpResponseServerError',
    'Http404', 'BadHeaderError', 'JsonResponse', 'FileResponse',
]