"""
Last-View：2019年8月9日06:49:57
View-Counter：1
"""

from django.core.exceptions import ImproperlyConfigured
from django.core.paginator import InvalidPage, Paginator
from django.db.models.query import QuerySet
from django.http import Http404
from django.utils.translation import gettext as _
from django.views.generic.base import ContextMixin, TemplateResponseMixin, View


class MultipleObjectMixin(ContextMixin):
    """ 
    多例 mixin.

    allow_empty = True
    queryset = None
    model = None
    paginate_by = None
    paginate_orphans = 0
    context_object_name = None
    paginator_class = Paginator
    page_kwarg = 'page'
    ordering = None
    """
    allow_empty = True
    queryset = None
    model = None
    paginate_by = None
    paginate_orphans = 0
    context_object_name = None
    paginator_class = Paginator
    page_kwarg = 'page'
    ordering = None

    def get_queryset(self):
        """
        返回给这个视图的对象列表
        
        返回值必须是可迭代对象 可以是查询集的实例 此时会调用特殊行为
        """
        if self.queryset is not None:
            queryset = self.queryset
            if isinstance(queryset, QuerySet):
                queryset = queryset.all()
        elif self.model is not None:
            # 不提供查询集默认是模型全部实例
            queryset = self.model._default_manager.all()
        else:
            raise ImproperlyConfigured(
                "%(cls)s is missing a QuerySet. Define "
                "%(cls)s.model, %(cls)s.queryset, or override "
                "%(cls)s.get_queryset()." % {
                    'cls': self.__class__.__name__
                }
            )
        ordering = self.get_ordering()
        if ordering:
            if isinstance(ordering, str):
                ordering = (ordering,)
            queryset = queryset.order_by(*ordering)

        return queryset

    def get_ordering(self):
        """返回排序字段或字段元组"""
        return self.ordering

    def paginate_queryset(self, queryset, page_size):
        """将查询集分页."""

        # 实例化分页器
        paginator = self.get_paginator(
            queryset, page_size, orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty())

        page_kwarg = self.page_kwarg
        # 从 url 参数或 GET 参数 或 1
        page = self.kwargs.get(page_kwarg) or self.request.GET.get(page_kwarg) or 1
        try:
            page_number = int(page)
        except ValueError:
            # 特别允许最后一页
            if page == 'last':
                page_number = paginator.num_pages
            else:
                raise Http404(_("Page is not 'last', nor can it be converted to an int."))
        try:
            page = paginator.page(page_number)
            # 正确分支 返回 （分页器 页对象 页内对象列表 还有页）
            return (paginator, page, page.object_list, page.has_other_pages())
        except InvalidPage as e:
            # 没有这一页
            raise Http404(_('Invalid page (%(page_number)s): %(message)s') % {
                'page_number': page_number,
                'message': str(e)
            })

    def get_paginate_by(self, queryset):
        """
        获取每页数量 默认 None 不分页
        """
        return self.paginate_by

    def get_paginator(self, queryset, per_page, orphans=0,
                      allow_empty_first_page=True, **kwargs):
        """返回一个分页器实例"""
        return self.paginator_class(
            queryset, per_page, orphans=orphans,
            allow_empty_first_page=allow_empty_first_page, **kwargs)

    def get_paginate_orphans(self):
        """
        尾页多出来的部分最大数量
        """
        return self.paginate_orphans

    def get_allow_empty(self):
        """
        可否为空
        """
        return self.allow_empty

    def get_context_object_name(self, object_list):
        """获取上下文里对象所用名称"""
        if self.context_object_name:
            return self.context_object_name
        elif hasattr(object_list, 'model'):
            ## 有 model 就用 model_name_list 可不提供
            return '%s_list' % object_list.model._meta.model_name
        else:
            return None

    def get_context_data(self, *, object_list=None, **kwargs):
        """获取当前视图的上下文数据"""
        queryset = object_list if object_list is not None else self.object_list
        ## get_paginate_by 默认没用 queryset。方便重写根据 queryset 大小返回 pagesize 
        page_size = self.get_paginate_by(queryset)
        context_object_name = self.get_context_object_name(queryset)
        if page_size:
            paginator, page, queryset, is_paginated = self.paginate_queryset(queryset, page_size)
            context = {
                'paginator': paginator,
                'page_obj': page,
                'is_paginated': is_paginated,
                'object_list': queryset
            }
        else:
            context = {
                'paginator': None,
                'page_obj': None,
                'is_paginated': False,
                'object_list': queryset
            }
        ## 这里做了双保险 皆可以用 object_list 访问
        if context_object_name is not None:
            context[context_object_name] = queryset
        ## 层层继承的时候用 update 增量传递上下文
        context.update(kwargs)
        return super().get_context_data(**context)


class BaseListView(MultipleObjectMixin, View):
    """一个用来展示对象列表的基本视图"""
    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        allow_empty = self.get_allow_empty()

        if not allow_empty:
            ## 可以分页 有查询集：做一个廉价查询比把整个查询集都加载到内存要好
            ## self.object_list.exists() 就是廉价查询

            if self.get_paginate_by(self.object_list) is not None and hasattr(self.object_list, 'exists'):
                is_empty = not self.object_list.exists()
            else:
                is_empty = not self.object_list
            ## 不允许为空确实空的返回404
            if is_empty:
                raise Http404(_("Empty list and '%(class_name)s.allow_empty' is False.") % {
                    'class_name': self.__class__.__name__,
                })
        context = self.get_context_data()
        ## render_to_response 是哪里继承来的
        ## MultipleObjectMixin, View里面都没有
        ## TemplateResponseMixin 里面有但是这里没有继承啊？？ 是不是BUG
        return self.render_to_response(context)


class MultipleObjectTemplateResponseMixin(TemplateResponseMixin):
    """用模板展示对象列表的 mixin"""
    template_name_suffix = '_list'

    def get_template_names(self):
        """
        返回模板名列表.
        render_to_response 重写了就不会调用.
        """
        try:
            names = super().get_template_names()
        except ImproperlyConfigured:
            ## 没有指定模板名也不要紧
            ## 我们从一个空列表开始
            names = []

        # 如果列表是查询集，我们根据 app 和 model 创造一个模板名
        # 放在列表最后 可被用户指定的重写
        if hasattr(self.object_list, 'model'):
            opts = self.object_list.model._meta
            ## 可见是按有子目录的
            names.append("%s/%s%s.html" % (opts.app_label, opts.model_name, self.template_name_suffix))
        elif not names:
            ## template_name 和 get_queryset 缺一不可
            raise ImproperlyConfigured(
                "%(cls)s requires either a 'template_name' attribute "
                "or a get_queryset() method that returns a QuerySet." % {
                    'cls': self.__class__.__name__,
                }
            )
        return names


class ListView(MultipleObjectTemplateResponseMixin, BaseListView):
    """
    不需要类主体 空的即可 也解答了上面的问题
    BaseListView 里的render_to_response 是 MultipleObjectTemplateResponseMixin里面的
    所以不能对外继承 只能继承 ListView

    model 和 queryset 二选一
    queryset 不一定是 QuerySet 实例；可迭代即可
    就算是 list 也可以被分页。
    """
