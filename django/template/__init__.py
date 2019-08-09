"""
django.template 包含两个独立的子系统

1. 多个模板引擎：支撑可插拔的模板后端
2. Django Template Language ：Django 自己的模板语言 
包含 loaders, context processors, tags and filters.

Django's support for templates.

The django.template namespace contains two independent subsystems:

1. Multiple Template Engines: support for pluggable template backends,
   built-in backends and backend-independent APIs
2. Django Template Language: Django's own template engine, including its
   built-in loaders, context processors, tags and filters.

Ideally these subsystems would be implemented in distinct packages. However
keeping them together made the implementation of Multiple Template Engines
less disruptive .

Here's a breakdown of which modules belong to which subsystem.

Multiple Template Engines:
其他模板引擎
- django.template.backends.*
- django.template.loader
- django.template.response

DTL 只需要学习这个
Django Template Language:

- django.template.base
- django.template.context
- django.template.context_processors
- django.template.loaders.*
- django.template.debug
- django.template.defaultfilters
- django.template.defaulttags
- django.template.engine
- django.template.loader_tags
- django.template.smartif

Shared:

- django.template.utils

"""

# Multiple Template Engines

from .engine import Engine
from .utils import EngineHandler

engines = EngineHandler()

__all__ = ('Engine', 'engines')


# Django Template Language

# Public exceptions
from .base import VariableDoesNotExist                                  # NOQA isort:skip
from .context import ContextPopException                                # NOQA isort:skip
from .exceptions import TemplateDoesNotExist, TemplateSyntaxError       # NOQA isort:skip

# Template parts
from .base import (                                                     # NOQA isort:skip
    Context, Node, NodeList, Origin, RequestContext, Template, Variable,
)

# Library management
from .library import Library                                            # NOQA isort:skip


__all__ += ('Template', 'Context', 'RequestContext')
