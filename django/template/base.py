# Last-Modified：2019年8月9日18:54:51
# View-Couter：1

"""
这是Django模板系统。

这个怎么运作：

Lexer.tokenize（）方法转换模板字符串（即字符串）
包含自定义模板标记的标记）到标记，可以是
纯文本（TokenType.TEXT），变量（TokenType.VAR）或块语句
（TokenType.BLOCK）。

Parser（）类在其构造函数中获取标记列表，并且其解析（）
方法返回一个已编译的模板 - 这是一个列表
节点对象。

每个节点负责创建某种输出 - 例如简单的文字
（TextNode），给定上下文中的变量值（VariableNode），基本结果
逻辑（IfNode），循环结果（ForNode）或其他任何东西。核心节点
类型是TextNode，VariableNode，IfNode和ForNode，但插件模块可以
定义自己的自定义节点类型。

每个Node都有一个render（）方法，它接受Context并返回一个字符串
渲染节点。例如，变量节点的render（）方法返回
变量的值为字符串。 ForNode的render（）方法返回
以递归方式呈现循环内部内容的输出。

Template类是一个方便的包装器，负责处理模板
编译和渲染。

用法：

您应该直接在此文件中使用的唯一内容是Template类。
使用template_string创建一个已编译的模板对象，然后调用render（）
有了背景。在编译阶段，TemplateSyntaxError异常
如果模板没有正确的语法，将会引发。

Sample code:

>>> from django import template
>>> s = '<html>{% if test %}<h1>{{ varvalue }}</h1>{% endif %}</html>'
>>> t = template.Template(s)

(t is now a compiled template, and its render() method can be called multiple
times with multiple contexts)

>>> c = template.Context({'test':True, 'varvalue': 'Hello'})
>>> t.render(c)
'<html><h1>Hello</h1></html>'
>>> c = template.Context({'test':False, 'varvalue': 'Hello'})
>>> t.render(c)
'<html></html>'
"""

import logging
import re
from enum import Enum
from inspect import getcallargs, getfullargspec, unwrap

from django.template.context import (  # NOQA: imported for backwards compatibility
    BaseContext, Context, ContextPopException, RequestContext,
)
from django.utils.formats import localize
from django.utils.html import conditional_escape, escape
from django.utils.safestring import SafeData, mark_safe
from django.utils.text import (
    get_text_list, smart_split, unescape_string_literal,
)
from django.utils.timezone import template_localtime
from django.utils.translation import gettext_lazy, pgettext_lazy

from .exceptions import TemplateSyntaxError

# template syntax constants
FILTER_SEPARATOR = '|'
FILTER_ARGUMENT_SEPARATOR = ':'
VARIABLE_ATTRIBUTE_SEPARATOR = '.'
BLOCK_TAG_START = '{%'
BLOCK_TAG_END = '%}'
VARIABLE_TAG_START = '{{'
VARIABLE_TAG_END = '}}'
COMMENT_TAG_START = '{#'
COMMENT_TAG_END = '#}'
TRANSLATOR_COMMENT_MARK = 'Translators'
SINGLE_BRACE_START = '{'
SINGLE_BRACE_END = '}'

# what to report as the origin for templates that come from non-loader sources
# (e.g. strings)
UNKNOWN_SOURCE = '<unknown source>'

# match a variable or block tag and capture the entire tag, including start/end
# delimiters

# 下面这个正则表达式找到各个块，也是节点{%%}|{{}}|{##}
tag_re = (re.compile('(%s.*?%s|%s.*?%s|%s.*?%s)' %
          (re.escape(BLOCK_TAG_START), re.escape(BLOCK_TAG_END),
           re.escape(VARIABLE_TAG_START), re.escape(VARIABLE_TAG_END),
           re.escape(COMMENT_TAG_START), re.escape(COMMENT_TAG_END))))

logger = logging.getLogger('django.template')


class TokenType(Enum):
    TEXT = 0
    VAR = 1
    BLOCK = 2
    COMMENT = 3


class VariableDoesNotExist(Exception):

    def __init__(self, msg, params=()):
        self.msg = msg
        self.params = params

    def __str__(self):
        return self.msg % self.params


class Origin:
    def __init__(self, name, template_name=None, loader=None):
        self.name = name
        self.template_name = template_name
        self.loader = loader

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return (
            isinstance(other, Origin) and
            self.name == other.name and
            self.loader == other.loader
        )

    @property
    def loader_name(self):
        if self.loader:
            return '%s.%s' % (
                self.loader.__module__, self.loader.__class__.__name__,
            )


class Template:
    def __init__(self, template_string, origin=None, name=None, engine=None):
        # If Template is instantiated directly rather than from an Engine and
        # exactly one Django template engine is configured, use that engine.
        # This is required to preserve backwards-compatibility for direct use
        # e.g. Template('...').render(Context({...}))
        # 如果模板是直接实例化而不是从引擎生成的
        # e.g. Template('...').render(Context({...}))
        if engine is None:
            from .engine import Engine
            engine = Engine.get_default()
        if origin is None:
            origin = Origin(UNKNOWN_SOURCE)
        self.name = name
        self.origin = origin
        self.engine = engine
        self.source = str(template_string)  # May be lazy.
        self.nodelist = self.compile_nodelist()

    def __iter__(self):
        # 模板是可迭代的
        for node in self.nodelist:
            yield from node

    def _render(self, context):
        # 调用了节点列表的渲染方法
        return self.nodelist.render(context)

    def render(self, context):
        "Display stage -- can be called many times"
        with context.render_context.push_state(self):
            if context.template is None:
                with context.bind_template(self):
                    context.template_name = self.name
                    return self._render(context)
            else:
                return self._render(context)

    def compile_nodelist(self):
        """
        解析和编译模板为节点列表
        Parse and compile the template source into a nodelist. If debug
        is True and an exception occurs during parsing, the exception is
        is annotated with contextual line information where it occurred in the
        template source.
        """
        if self.engine.debug:
            lexer = DebugLexer(self.source)
        else:
            lexer = Lexer(self.source)

        tokens = lexer.tokenize()

        # 解析器
        parser = Parser(
            tokens, self.engine.template_libraries, self.engine.template_builtins,
            self.origin,
        )

        try:
            return parser.parse()
        except Exception as e:
            if self.engine.debug:
                e.template_debug = self.get_exception_info(e, e.token)
            raise

    def get_exception_info(self, exception, token):
        """
        DUBUG 时返回错误行
        Return a dictionary containing contextual line information of where
        the exception occurred in the template. The following information is
        provided:

        message
            The message of the exception raised.

        source_lines
            The lines before, after, and including the line the exception
            occurred on.

        line
            The line number the exception occurred on.

        before, during, after
            The line the exception occurred on split into three parts:
            1. The content before the token that raised the error.
            2. The token that raised the error.
            3. The content after the token that raised the error.

        total
            The number of lines in source_lines.

        top
            The line number where source_lines starts.

        bottom
            The line number where source_lines ends.

        start
            The start position of the token in the template source.

        end
            The end position of the token in the template source.
        """
        start, end = token.position
        context_lines = 10
        line = 0
        upto = 0
        source_lines = []
        before = during = after = ""
        for num, next in enumerate(linebreak_iter(self.source)):
            if start >= upto and end <= next:
                line = num
                before = escape(self.source[upto:start])
                during = escape(self.source[start:end])
                after = escape(self.source[end:next])
            source_lines.append((num, escape(self.source[upto:next])))
            upto = next
        total = len(source_lines)

        top = max(1, line - context_lines)
        bottom = min(total, line + 1 + context_lines)

        # In some rare cases exc_value.args can be empty or an invalid
        # string.
        try:
            message = str(exception.args[0])
        except (IndexError, UnicodeDecodeError):
            message = '(Could not get exception message)'

        return {
            'message': message,
            'source_lines': source_lines[top:bottom],
            'before': before,
            'during': during,
            'after': after,
            'top': top,
            'bottom': bottom,
            'total': total,
            'line': line,
            'name': self.origin.name,
            'start': start,
            'end': end,
        }


def linebreak_iter(template_source):
    """行数生成器"""
    yield 0
    p = template_source.find('\n')
    while p >= 0:
        yield p + 1
        p = template_source.find('\n', p + 1)
    yield len(template_source) + 1


class Token:
    def __init__(self, token_type, contents, position=None, lineno=None):
        """
        一个 token 表示模板里的一个字符串

        token_type
            4种 TokenType类
            A TokenType, either .TEXT, .VAR, .BLOCK, or .COMMENT.

        contents
            元字符串
            The token source string.

        position
            位置
            An optional tuple containing the start and end index of the token
            in the template source. This is used for traceback information
            when debug is on.

        lineno
            行号
            The line number the token appears on in the template source.
            This is used for traceback information and gettext files.
        """
        self.token_type, self.contents = token_type, contents
        self.lineno = lineno
        self.position = position

    def __str__(self):
        token_name = self.token_type.name.capitalize()
        return ('<%s token: "%s...">' %
                (token_name, self.contents[:20].replace('\n', '')))

    def split_contents(self):
        split = []
        # 将内容智能拆分
        bits = smart_split(self.contents)
        for bit in bits:
            # Handle translation-marked template pieces
            if bit.startswith(('_("', "_('")):
                sentinel = bit[2] + ')'
                trans_bit = [bit]
                while not bit.endswith(sentinel):
                    bit = next(bits)
                    trans_bit.append(bit)
                bit = ' '.join(trans_bit)
            split.append(bit)
        return split


class Lexer:
    def __init__(self, template_string):
        self.template_string = template_string
        self.verbatim = False  #逐字

    def tokenize(self):
        """
        给定模板返回一列token
        Return a list of tokens from a given template_string.
        """
        in_tag = False
        lineno = 1
        result = []

        # 用 tag_re 拆分原模板 所得为 TEXT 和 BOLCK 等
        for bit in tag_re.split(self.template_string):
            if bit:
                result.append(self.create_token(bit, None, lineno, in_tag))
            # 以下都是 bit 为空的时候
            in_tag = not in_tag
            lineno += bit.count('\n')
        return result

    def create_token(self, token_string, position, lineno, in_tag):
        """
        把 token 字符串转化成 Token 对象返回
        如果 in_tag 为 True 处理匹配到的Tag
        否则就是普通字符串
        """
        # BLOCK块{%%}
        if in_tag and token_string.startswith(BLOCK_TAG_START):
            # The [2:-2] ranges below strip off *_TAG_START and *_TAG_END.
            # We could do len(BLOCK_TAG_START) to be more "correct", but we've
            # hard-coded the 2s here for performance. And it's not like
            # the TAG_START values are going to change anytime, anyway.

            # 这里是为了性能硬编码了TAG开始长度为2
            block_content = token_string[2:-2].strip()
            if self.verbatim and block_content == self.verbatim:
                self.verbatim = False
        if in_tag and not self.verbatim:
            # 变量块{{}}
            if token_string.startswith(VARIABLE_TAG_START):
                return Token(TokenType.VAR, token_string[2:-2].strip(), position, lineno)
            # BLOCK块{%%}    
            elif token_string.startswith(BLOCK_TAG_START):
                ## 原来是 {% verbatim %}
                if block_content[:9] in ('verbatim', 'verbatim '):
                    self.verbatim = 'end%s' % block_content
                return Token(TokenType.BLOCK, block_content, position, lineno)
            # Comment块{##}
            elif token_string.startswith(COMMENT_TAG_START):
                content = ''
                if token_string.find(TRANSLATOR_COMMENT_MARK):
                    content = token_string[2:-2].strip()
                return Token(TokenType.COMMENT, content, position, lineno)
        else:
            # 文本这里不单是html文本 所有文本均可
            return Token(TokenType.TEXT, token_string, position, lineno)


class DebugLexer(Lexer):
    def tokenize(self):
        """
        Split a template string into tokens and annotates each token with its
        start and end position in the source. This is slower than the default
        lexer so only use it when debug is True.
        """
        lineno = 1
        result = []
        upto = 0
        for match in tag_re.finditer(self.template_string):
            start, end = match.span()
            if start > upto:
                token_string = self.template_string[upto:start]
                result.append(self.create_token(token_string, (upto, start), lineno, in_tag=False))
                lineno += token_string.count('\n')
                upto = start
            token_string = self.template_string[start:end]
            result.append(self.create_token(token_string, (start, end), lineno, in_tag=True))
            lineno += token_string.count('\n')
            upto = end
        last_bit = self.template_string[upto:]
        if last_bit:
            result.append(self.create_token(last_bit, (upto, upto + len(last_bit)), lineno, in_tag=False))
        return result


class Parser:
    def __init__(self, tokens, libraries=None, builtins=None, origin=None):
        self.tokens = tokens
        self.tags = {}
        self.filters = {}
        self.command_stack = []

        if libraries is None:
            libraries = {}
        if builtins is None:
            builtins = []

        self.libraries = libraries
        for builtin in builtins:
            self.add_library(builtin) # 加入内置的过滤器
        self.origin = origin

    def parse(self, parse_until=None):
        """
        迭代 tokens 编译每一个为一个节点
        Iterate through the parser tokens and compiles each one into a node.

        If parse_until is provided, parsing will stop once one of the
        specified tokens has been reached. This is formatted as a list of
        tokens, e.g. ['elif', 'else', 'endif']. If no matching token is
        reached, raise an exception with the unclosed block tag details.
        """
        if parse_until is None:
            parse_until = []
        nodelist = NodeList()
        while self.tokens:
            token = self.next_token()
            # Use the raw values here for TokenType.* for a tiny performance boost.
            # 提高性能的方法
            if token.token_type.value == 0:  # TokenType.TEXT
                self.extend_nodelist(nodelist, TextNode(token.contents), token)
            elif token.token_type.value == 1:  # TokenType.VAR
                if not token.contents:
                    raise self.error(token, 'Empty variable tag on line %d' % token.lineno)
                try:
                    # 编译过滤器
                    filter_expression = self.compile_filter(token.contents)
                except TemplateSyntaxError as e:
                    raise self.error(token, e)
                # 完成后的节点
                var_node = VariableNode(filter_expression)
                self.extend_nodelist(nodelist, var_node, token)
            elif token.token_type.value == 2:  # TokenType.BLOCK
                try:
                    command = token.contents.split()[0] # 第一个单词为命令
                except IndexError:
                    raise self.error(token, 'Empty block tag on line %d' % token.lineno)

                # command 是 {% endif %} 这种停止符
                if command in parse_until:
                    # A matching token has been reached. Return control to
                    # the caller. Put the token back on the token list so the
                    # caller knows where it terminated.
                    self.prepend_token(token)
                    return nodelist
                # Add the token to the command stack. This is used for error
                # messages if further parsing fails due to an unclosed block
                # tag.
                # 将命令和 token 压栈 算法同有效括号匹配
                self.command_stack.append((command, token))
                # Get the tag callback function from the ones registered with
                # the parser.
                try:
                    # 映射 command 字符串到 tags 里的函数
                    compile_func = self.tags[command]
                except KeyError:
                    self.invalid_block_tag(token, command, parse_until)
                
                # 编译执行这个 tag 函数返回节点 这里也说明了 tag 函数只接受 token 为参数
                try:
                    compiled_result = compile_func(self, token)
                except Exception as e:
                    raise self.error(token, e)
                self.extend_nodelist(nodelist, compiled_result, token)
                # 这段编译成功弹栈
                self.command_stack.pop()

        # 剩下不匹配的 parse_until 报错
        if parse_until:
            self.unclosed_block_tag(parse_until)
        return nodelist

    def skip_past(self, endtag):
        while self.tokens:
            token = self.next_token()
            if token.token_type == TokenType.BLOCK and token.contents == endtag:
                return
        self.unclosed_block_tag([endtag])

    def extend_nodelist(self, nodelist, node, token):
        # Check that non-text nodes don't appear before an extends tag.
        if node.must_be_first and nodelist.contains_nontext:
            raise self.error(
                token, '%r must be the first tag in the template.' % node,
            )
        if isinstance(nodelist, NodeList) and not isinstance(node, TextNode):
            nodelist.contains_nontext = True
        # Set origin and token here since we can't modify the node __init__()
        # method.
        node.token = token
        node.origin = self.origin
        nodelist.append(node)

    def error(self, token, e):
        """
        Return an exception annotated with the originating token. Since the
        parser can be called recursively, check if a token is already set. This
        ensures the innermost token is highlighted if an exception occurs,
        e.g. a compile error within the body of an if statement.
        """
        if not isinstance(e, Exception):
            e = TemplateSyntaxError(e)
        if not hasattr(e, 'token'):
            e.token = token
        return e

    def invalid_block_tag(self, token, command, parse_until=None):
        if parse_until:
            raise self.error(
                token,
                "Invalid block tag on line %d: '%s', expected %s. Did you "
                "forget to register or load this tag?" % (
                    token.lineno,
                    command,
                    get_text_list(["'%s'" % p for p in parse_until], 'or'),
                ),
            )
        raise self.error(
            token,
            "Invalid block tag on line %d: '%s'. Did you forget to register "
            "or load this tag?" % (token.lineno, command)
        )

    def unclosed_block_tag(self, parse_until):
        command, token = self.command_stack.pop()
        msg = "Unclosed tag on line %d: '%s'. Looking for one of: %s." % (
            token.lineno,
            command,
            ', '.join(parse_until),
        )
        raise self.error(token, msg)

    def next_token(self):
        # self.tokens [] 从左开始取
        return self.tokens.pop(0)

    def prepend_token(self, token):
        # 把 结束标记插入左端
        self.tokens.insert(0, token)

    def delete_first_token(self):
        del self.tokens[0]

    def add_library(self, lib):
        """加入自定义的tags"""
        self.tags.update(lib.tags)
        self.filters.update(lib.filters)

    def compile_filter(self, token):
        """
        包装了过滤器表达式 FilterExpression 是个表达式解释器
        """
        return FilterExpression(token, self)

    def find_filter(self, filter_name):
        if filter_name in self.filters:
            return self.filters[filter_name]
        else:
            raise TemplateSyntaxError("Invalid filter: '%s'" % filter_name)


# This only matches constant *strings* (things in quotes or marked for
# translation). Numbers are treated as variables for implementation reasons
# (so that they retain their type when passed to filters).
constant_string = r"""
(?:%(i18n_open)s%(strdq)s%(i18n_close)s|
%(i18n_open)s%(strsq)s%(i18n_close)s|
%(strdq)s|
%(strsq)s)
""" % {
    'strdq': r'"[^"\\]*(?:\\.[^"\\]*)*"',  # double-quoted string
    'strsq': r"'[^'\\]*(?:\\.[^'\\]*)*'",  # single-quoted string
    'i18n_open': re.escape("_("),
    'i18n_close': re.escape(")"),
}
constant_string = constant_string.replace("\n", "")

filter_raw_string = r"""
^(?P<constant>%(constant)s)|
^(?P<var>[%(var_chars)s]+|%(num)s)|
 (?:\s*%(filter_sep)s\s*
     (?P<filter_name>\w+)
         (?:%(arg_sep)s
             (?:
              (?P<constant_arg>%(constant)s)|
              (?P<var_arg>[%(var_chars)s]+|%(num)s)
             )
         )?
 )""" % {
    'constant': constant_string,
    'num': r'[-+\.]?\d[\d\.e]*',
    'var_chars': r'\w\.',
    'filter_sep': re.escape(FILTER_SEPARATOR),
    'arg_sep': re.escape(FILTER_ARGUMENT_SEPARATOR),
}

filter_re = re.compile(filter_raw_string, re.VERBOSE)


class FilterExpression:
    """
    解析变量 token 和 过滤器 当成一个字符串
    返回 过滤器名和参数
    Parse a variable token and its optional filters (all as a single string),
    and return a list of tuples of the filter name and arguments.
    Sample::

        >>> token = 'variable|default:"Default value"|date:"Y-m-d"'
        >>> p = Parser('')
        >>> fe = FilterExpression(token, p)
        >>> len(fe.filters)
        2
        >>> fe.var
        <Variable: 'variable'>
    """
    def __init__(self, token, parser):
        self.token = token
        matches = filter_re.finditer(token)
        var_obj = None
        filters = []
        upto = 0
        for match in matches:
            start = match.start()
            if upto != start:
                raise TemplateSyntaxError("Could not parse some characters: "
                                          "%s|%s|%s" %
                                          (token[:upto], token[upto:start],
                                           token[start:]))
            if var_obj is None:
                var, constant = match.group("var", "constant")
                if constant:
                    try:
                        var_obj = Variable(constant).resolve({})
                    except VariableDoesNotExist:
                        var_obj = None
                elif var is None:
                    raise TemplateSyntaxError("Could not find variable at "
                                              "start of %s." % token)
                else:
                    var_obj = Variable(var)
            else:
                filter_name = match.group("filter_name")
                args = []
                constant_arg, var_arg = match.group("constant_arg", "var_arg")
                if constant_arg:
                    args.append((False, Variable(constant_arg).resolve({})))
                elif var_arg:
                    args.append((True, Variable(var_arg)))
                # 过滤器函数
                filter_func = parser.find_filter(filter_name)
                # 参数检查
                self.args_check(filter_name, filter_func, args)
                # 过滤器栈
                filters.append((filter_func, args))
            upto = match.end()
        if upto != len(token):
            raise TemplateSyntaxError("Could not parse the remainder: '%s' "
                                      "from '%s'" % (token[upto:], token))
        # 中间有计算的话一般在最后一步赋值给 self
        self.filters = filters
        self.var = var_obj

    def resolve(self, context, ignore_failures=False):
        if isinstance(self.var, Variable):
            try:
                obj = self.var.resolve(context)
            except VariableDoesNotExist:
                if ignore_failures:
                    obj = None
                else:
                    string_if_invalid = context.template.engine.string_if_invalid
                    if string_if_invalid:
                        if '%s' in string_if_invalid:
                            return string_if_invalid % self.var
                        else:
                            return string_if_invalid
                    else:
                        obj = string_if_invalid
        else:
            obj = self.var
        # 链式执行所有过滤器
        for func, args in self.filters:
            arg_vals = []
            for lookup, arg in args:
                if not lookup:
                    arg_vals.append(mark_safe(arg))
                else:
                    arg_vals.append(arg.resolve(context))
            if getattr(func, 'expects_localtime', False):
                obj = template_localtime(obj, context.use_tz)
            if getattr(func, 'needs_autoescape', False):
                new_obj = func(obj, autoescape=context.autoescape, *arg_vals)
            else:
                new_obj = func(obj, *arg_vals)

            # 下面这句保证了有 is_safe=True 的对象输出不用 mark_safe 二选一即可
            if getattr(func, 'is_safe', False) and isinstance(obj, SafeData):
                obj = mark_safe(new_obj)
            else:
                obj = new_obj
        return obj

    def args_check(name, func, provided):
        provided = list(provided)
        # First argument, filter input, is implied.
        plen = len(provided) + 1
        # 解除装饰器
        func = unwrap(func)

        args, _, _, defaults, _, _, _ = getfullargspec(func)
        alen = len(args)
        dlen = len(defaults or [])
        # Not enough OR Too many
        if plen < (alen - dlen) or plen > alen:
            raise TemplateSyntaxError("%s requires %d arguments, %d provided" %
                                      (name, alen - dlen, plen))

        return True
    # 静态方法为什么不用@staticmethod
    args_check = staticmethod(args_check)

    def __str__(self):
        return self.token


class Variable:
    """
    模板变量|使用context|可解析的|可以是硬编码字符串
    A template variable, resolvable against a given context. The variable may
    be a hard-coded string (if it begins and ends with single or double quote
    marks)::

        >>> c = {'article': {'section':'News'}}
        >>> Variable('article.section').resolve(c)
        'News'
        >>> Variable('article').resolve(c)
        {'section': 'News'}
        >>> class AClass: pass
        >>> c = AClass()
        >>> c.article = AClass()
        >>> c.article.section = 'News'

    (The example assumes VARIABLE_ATTRIBUTE_SEPARATOR is '.')
    """

    def __init__(self, var):
        self.var = var
        self.literal = None
        self.lookups = None
        self.translate = False
        self.message_context = None

        if not isinstance(var, str):
            raise TypeError(
                "Variable must be a string or number, got %s" % type(var))
        try:
            # First try to treat this variable as a number.
            #
            # Note that this could cause an OverflowError here that we're not
            # catching. Since this should only happen at compile time, that's
            # probably OK.

            # Try to interpret values containing a period or an 'e'/'E'
            # (possibly scientific notation) as a float;  otherwise, try int.
            if '.' in var or 'e' in var.lower():
                self.literal = float(var)
                # "2." is invalid
                if var.endswith('.'):
                    raise ValueError
            else:
                self.literal = int(var)
        except ValueError:
            # A ValueError means that the variable isn't a number.
            if var.startswith('_(') and var.endswith(')'):
                # The result of the lookup should be translated at rendering
                # time.
                self.translate = True
                var = var[2:-1]
            # If it's wrapped with quotes (single or double), then
            # we're also dealing with a literal.
            try:
                self.literal = mark_safe(unescape_string_literal(var))
            except ValueError:
                # Otherwise we'll set self.lookups so that resolve() knows we're
                # dealing with a bonafide variable
                if var.find(VARIABLE_ATTRIBUTE_SEPARATOR + '_') > -1 or var[0] == '_':
                    raise TemplateSyntaxError("Variables and attributes may "
                                              "not begin with underscores: '%s'" %
                                              var)
                self.lookups = tuple(var.split(VARIABLE_ATTRIBUTE_SEPARATOR))

    def resolve(self, context):
        """Resolve this variable against a given context."""
        if self.lookups is not None:
            # 处理的是变量需要被解析
            value = self._resolve_lookup(context)
        else:
            # We're dealing with a literal, so it's already been "resolved"
            value = self.literal
        # 是否需要翻译
        if self.translate:
            is_safe = isinstance(value, SafeData)
            msgid = value.replace('%', '%%')
            msgid = mark_safe(msgid) if is_safe else msgid
            if self.message_context:
                return pgettext_lazy(self.message_context, msgid)
            else:
                return gettext_lazy(msgid)
        return value

    def __repr__(self):
        return "<%s: %r>" % (self.__class__.__name__, self.var)

    def __str__(self):
        return self.var

    def _resolve_lookup(self, context):
        """
        根据 context 解析出真实的变量而不是字符串 {{ xxx }}
        查询方式依次是
        字典：context[xxx]
        属性：context.xxx.xx
        可调用方法：context.xxx.f()

        Perform resolution of a real variable (i.e. not a literal) against the
        given context.

        As indicated by the method's name, this method is an implementation
        detail and shouldn't be called by external code. Use Variable.resolve()
        instead.
        """
        current = context
        try:  # catch-all for silent variable failures
            for bit in self.lookups:
                try:  # dictionary lookup
                    current = current[bit] #这是一个连续查找的过程
                    # ValueError/IndexError are for numpy.array lookup on
                    # numpy < 1.9 and 1.9+ respectively
                except (TypeError, AttributeError, KeyError, ValueError, IndexError):
                    try:  # attribute lookup
                        # 如果是 context 类 不要返回类属性:
                        if isinstance(current, BaseContext) and getattr(type(current), bit):
                            raise AttributeError
                        current = getattr(current, bit)
                    except (TypeError, AttributeError):
                        # Reraise if the exception was raised by a @property
                        if not isinstance(current, BaseContext) and bit in dir(current):
                            raise
                        try:  # list-index lookup
                            # 下标查询 这意味着 {{ a.b.'0'}} 是合法的
                            current = current[int(bit)]
                        except (IndexError,  # list index out of range
                                ValueError,  # invalid literal for int()
                                KeyError,    # current is a dict without `int(bit)` key
                                TypeError):  # unsubscriptable object
                            raise VariableDoesNotExist("Failed lookup for key "
                                                       "[%s] in %r",
                                                       (bit, current))  # missing attribute
                # 如果 current 可调用
                if callable(current):
                    # current 对象有 do_not_call_in_templates 时可扩展
                    if getattr(current, 'do_not_call_in_templates', False):
                        pass
                    elif getattr(current, 'alters_data', False):
                        current = context.template.engine.string_if_invalid
                    else:
                        try:  # method call (assuming no args required)
                            # 调用方法 假设没有参数 有参数的就没办法了
                            # 如果要加入对参数的支持可以怎么做,用分隔符__
                            # x.fun(a,b) >>> x.fun__a__b
                            # x.fun(a,key=3) >>> x.fun__a__key_3
                            # 可以单没必要 这一步应该在 view 里实现，直接
                            # 给每个对象加上一个可调用的无参数方法即可 即时计算出来
                            # 也可以直接加个属性 
                            # for x in xlist:
                            #     x.fun = fun(x,a=c) #用偏函数实现
                            # {'xlist':xlist} 
                            current = current()
                        except TypeError:
                            try:
                                getcallargs(current)
                            except TypeError:  # arguments *were* required
                                current = context.template.engine.string_if_invalid  # invalid method call
                            else:
                                raise
        except Exception as e:
            template_name = getattr(context, 'template_name', None) or 'unknown'
            logger.debug(
                "Exception while resolving variable '%s' in template '%s'.",
                bit,
                template_name,
                exc_info=True,
            )
            # 静默处理模板错误
            if getattr(e, 'silent_variable_failure', False):
                current = context.template.engine.string_if_invalid
            else:
                raise

        return current


class Node:
    # Set this to True for nodes that must be first in the template (although
    # they can be preceded by text nodes.

    must_be_first = False  # 必须是第一个|不包括文本节点
    child_nodelists = ('nodelist',)  # 子节点
    token = None

    def render(self, context):
        """
        直接解析节点|没有实现|需要在子类中实现
        Return the node rendered as a string.
        """
        pass

    def render_annotated(self, context):
        """
        Render the node. If debug is True and an exception occurs during
        rendering, the exception is annotated with contextual line information
        where it occurred in the template. For internal usage this method is
        preferred over using the render method directly.
        """
        try:
            return self.render(context)
        except Exception as e:
            if context.template.engine.debug and not hasattr(e, 'template_debug'):
                e.template_debug = context.render_context.template.get_exception_info(e, self.token)
            raise

    def __iter__(self):
        # 可迭代
        yield self

    def get_nodes_by_type(self, nodetype):
        """
        返回本节点内部（包括自己）的全部 nodetype 节点
        """
        nodes = []
        if isinstance(self, nodetype):
            nodes.append(self)
        for attr in self.child_nodelists:
            # 应该是防止硬编码的
            nodelist = getattr(self, attr, None)
            if nodelist:
                # 这里递归调用 但不是树 extend是扁平结构
                nodes.extend(nodelist.get_nodes_by_type(nodetype))
        return nodes


class NodeList(list):
    # Set to True the first time a non-TextNode is inserted by
    # extend_nodelist().
    contains_nontext = False

    def render(self, context):
        """这里渲染了所有节点"""
        bits = []
        for node in self:
            if isinstance(node, Node):
                bit = node.render_annotated(context)
            else:
                bit = node
            bits.append(str(bit))
        return mark_safe(''.join(bits))

    def get_nodes_by_type(self, nodetype):
        "Return a list of all nodes of the given type"
        nodes = []
        for node in self:
            # 节点列表里面的递归 extend 是扁平结构不是树
            nodes.extend(node.get_nodes_by_type(nodetype))
        return nodes


class TextNode(Node):
    def __init__(self, s):
        self.s = s

    def __repr__(self):
        return "<%s: %r>" % (self.__class__.__name__, self.s[:25])

    def render(self, context):
        return self.s


def render_value_in_context(value, context):
    """
    把所有的值都渲染成模板的一部分|意味着转义
    Convert any value to a string to become part of a rendered template. This
    means escaping, if required, and conversion to a string. If value is a
    string, it's expected to already be translated.
    """
    value = template_localtime(value, use_tz=context.use_tz)
    value = localize(value, use_l10n=context.use_l10n)
    if context.autoescape:
        if not issubclass(type(value), str):
            value = str(value)
        return conditional_escape(value)
    else:
        return str(value)


class VariableNode(Node):
    """
    变量节点要用过滤器计算
    """
    def __init__(self, filter_expression):
        self.filter_expression = filter_expression

    def __repr__(self):
        return "<Variable Node: %s>" % self.filter_expression

    def render(self, context):
        try:
            output = self.filter_expression.resolve(context)
        except UnicodeDecodeError:
            # Unicode conversion can fail sometimes for reasons out of our
            # control (e.g. exception rendering). In that case, we fail
            # quietly.
            return ''
            # 把输出再 根据 context 里是否翻译和本地化处理一遍
        return render_value_in_context(output, context)


# Regex for token keyword arguments
kwarg_re = re.compile(r"(?:(\w+)=)?(.+)")


def token_kwargs(bits, parser, support_legacy=False):
    """
    解析关键字参数并且返回字典
    Parse token keyword arguments and return a dictionary of the arguments
    retrieved from the ``bits`` token list.

    `bits` is a list containing the remainder of the token (split by spaces)
    that is to be checked for arguments. Valid arguments are removed from this
    list.

    `support_legacy` - if True, the legacy format ``1 as foo`` is accepted.
    Otherwise, only the standard ``foo=1`` format is allowed.

    There is no requirement for all remaining token ``bits`` to be keyword
    arguments, so return the dictionary as soon as an invalid argument format
    is reached.
    """
    if not bits:
        return {}
    match = kwarg_re.match(bits[0])
    kwarg_format = match and match.group(1)
    if not kwarg_format:
        if not support_legacy:
            return {}
        if len(bits) < 3 or bits[1] != 'as':
            return {}

    kwargs = {}
    while bits:
        if kwarg_format:
            match = kwarg_re.match(bits[0])
            if not match or not match.group(1):
                return kwargs
            key, value = match.groups()
            del bits[:1]
        else:
            if len(bits) < 3 or bits[1] != 'as':
                return kwargs
            key, value = bits[2], bits[0]
            del bits[:3]
        kwargs[key] = parser.compile_filter(value)
        if bits and not kwarg_format:
            if bits[0] != 'and':
                return kwargs
            del bits[:1]
    return kwargs
