# Last-Modified：2019年8月9日19:43:42
# View-Couter：1

""" 上下文字典类"""

from contextlib import contextmanager
from copy import copy

# Hard-coded processor for easier use of CSRF protection.
_builtin_context_processors = ('django.template.context_processors.csrf',)


class ContextPopException(Exception):
    "pop() has been called more times than push()"
    pass


class ContextDict(dict):
    """实现了上下文管理器的字典"""
    def __init__(self, context, *args, **kwargs):
        super().__init__(*args, **kwargs) # 这里把**kwargs转换成了字典

        context.dicts.append(self) #加给了自己
        self.context = context # 本质上是字典列表

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.context.pop()


class BaseContext:
    """一个表现的像字典的字典列表"""
    def __init__(self, dict_=None):
        self._reset_dicts(dict_)

    def _reset_dicts(self, value=None):
        builtins = {'True': True, 'False': False, 'None': None}
        self.dicts = [builtins]
        if value is not None:
            self.dicts.append(value)

    def __copy__(self):
        duplicate = copy(super())
        duplicate.dicts = self.dicts[:]
        return duplicate

    def __repr__(self):
        return repr(self.dicts)

    def __iter__(self):
        return reversed(self.dicts)

    def push(self, *args, **kwargs):
        dicts = []
        for d in args:
            if isinstance(d, BaseContext):
                dicts += d.dicts[1:]  #是基本上下文就连接字典列表去掉builtins
            else:
                dicts.append(d)
        # 给self增加了context字典列表
        # 并且返回的 self
        return ContextDict(self, *dicts, **kwargs)

    def pop(self):
        if len(self.dicts) == 1:
            raise ContextPopException
        return self.dicts.pop()

    def __setitem__(self, key, value):
        # 修改当前上下文的值
        "Set a variable in the current context"
        self.dicts[-1][key] = value

    def set_upward(self, key, value):
        """
        设置最高级上下文的键值
        Set a variable in one of the higher contexts if it exists there,
        otherwise in the current context.
        """
        context = self.dicts[-1]
        for d in reversed(self.dicts):
            if key in d:
                context = d
                break
        context[key] = value

    def __getitem__(self, key):
        # 当前往上查找 d[key]
        "Get a variable's value, starting at the current context and going upward"
        for d in reversed(self.dicts):
            if key in d:
                return d[key]
        raise KeyError(key)

    def __delitem__(self, key):
        # 删除当前上下文里的键
        "Delete a variable from the current context"
        del self.dicts[-1][key]

    def __contains__(self, key):
        return any(key in d for d in self.dicts)

    def get(self, key, otherwise=None):
        for d in reversed(self.dicts):
            if key in d:
                return d[key]
        return otherwise

    def setdefault(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            self[key] = default
        return default

    def new(self, values=None):
        """
        Return a new context with the same properties, but with only the
        values given in 'values' stored.
        """
        new_context = copy(self)
        new_context._reset_dicts(values)
        return new_context

    def flatten(self):
        """
        碾平字典列表返回单个字典
        Return self.dicts as one dictionary.
        """
        flat = {}
        for d in self.dicts:
            flat.update(d)
        return flat

    def __eq__(self, other):
        """
        Compare two contexts by comparing theirs 'dicts' attributes.
        """
        return (
            isinstance(other, BaseContext) and
            # because dictionaries can be put in different order
            # we have to flatten them like in templates
            self.flatten() == other.flatten()
        )


class Context(BaseContext):
    # 可变上下文的栈
    "A stack container for variable context"
    def __init__(self, dict_=None, autoescape=True, use_l10n=None, use_tz=None):
        self.autoescape = autoescape
        self.use_l10n = use_l10n
        self.use_tz = use_tz
        self.template_name = "unknown"
        self.render_context = RenderContext()
        # Set to the original template -- as opposed to extended or included
        # templates -- during rendering, see bind_template.
        self.template = None
        super().__init__(dict_)

    @contextmanager
    def bind_template(self, template):
        if self.template is not None:
            raise RuntimeError("Context is already bound to a template")
        self.template = template
        try:
            yield
        finally:
            self.template = None

    def __copy__(self):
        duplicate = super().__copy__()
        duplicate.render_context = copy(self.render_context)
        return duplicate

    def update(self, other_dict):
        "Push other_dict to the stack of dictionaries in the Context"
        if not hasattr(other_dict, '__getitem__'):
            raise TypeError('other_dict must be a mapping (dictionary-like) object.')
        if isinstance(other_dict, BaseContext):
            other_dict = other_dict.dicts[1:].pop()
        return ContextDict(self, other_dict)


class RenderContext(BaseContext):
    """
    A stack container for storing Template state.

    RenderContext simplifies the implementation of template Nodes by providing a
    safe place to store state between invocations of a node's `render` method.

    The RenderContext also provides scoping rules that are more sensible for
    'template local' variables. The render context stack is pushed before each
    template is rendered, creating a fresh scope with nothing in it. Name
    resolution fails if a variable is not found at the top of the RequestContext
    stack. Thus, variables are local to a specific template and don't affect the
    rendering of other templates as they would if they were stored in the normal
    template context.
    """
    template = None

    def __iter__(self):
        yield from self.dicts[-1]

    def __contains__(self, key):
        return key in self.dicts[-1]

    def get(self, key, otherwise=None):
        return self.dicts[-1].get(key, otherwise)

    def __getitem__(self, key):
        return self.dicts[-1][key]

    @contextmanager
    def push_state(self, template, isolated_context=True):
        initial = self.template
        self.template = template
        if isolated_context:
            self.push()
        try:
            yield
        finally:
            self.template = initial
            if isolated_context:
                self.pop()


class RequestContext(Context):
    """
    This subclass of template.Context automatically populates itself using
    the processors defined in the engine's configuration.
    Additional processors can be specified as a list of callables
    using the "processors" keyword argument.
    """
    def __init__(self, request, dict_=None, processors=None, use_l10n=None, use_tz=None, autoescape=True):
        super().__init__(dict_, use_l10n=use_l10n, use_tz=use_tz, autoescape=autoescape)
        self.request = request
        self._processors = () if processors is None else tuple(processors)
        self._processors_index = len(self.dicts)

        # placeholder for context processors output
        self.update({})

        # empty dict for any new modifications
        # (so that context processors don't overwrite them)
        self.update({})

    @contextmanager
    def bind_template(self, template):
        if self.template is not None:
            raise RuntimeError("Context is already bound to a template")

        self.template = template
        # Set context processors according to the template engine's settings.
        processors = (template.engine.template_context_processors +
                      self._processors)
        updates = {}
        for processor in processors:
            updates.update(processor(self.request))
        self.dicts[self._processors_index] = updates

        try:
            yield
        finally:
            self.template = None
            # Unset context processors.
            self.dicts[self._processors_index] = {}

    def new(self, values=None):
        new_context = super().new(values)
        # This is for backwards-compatibility: RequestContexts created via
        # Context.new don't include values from context processors.
        if hasattr(new_context, '_processors_index'):
            del new_context._processors_index
        return new_context


def make_context(context, request=None, **kwargs):
    """
    用 dict 和可选的 HttpRequest 创建上下文对象
    Create a suitable Context from a plain dict and optionally an HttpRequest.
    """
    if context is not None and not isinstance(context, dict):
        raise TypeError('context must be a dict rather than %s.' % context.__class__.__name__)
    if request is None:
        context = Context(context, **kwargs)
    else:
        # The following pattern is required to ensure values from
        # context override those from template context processors.
        original_context = context
        context = RequestContext(request, **kwargs)
        if original_context:
            context.push(original_context)
    return context
