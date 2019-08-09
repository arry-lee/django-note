"""
Last-View：2019年8月9日07:29:28
View-Counter：1
"""

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.http import Http404
from django.utils.translation import gettext as _
from django.views.generic.base import ContextMixin, TemplateResponseMixin, View


class SingleObjectMixin(ContextMixin):
    """
    获取操作单个对象的能力
    model = None
    queryset = None
    slug_field = 'slug'
    context_object_name = None
    slug_url_kwarg = 'slug'
    pk_url_kwarg = 'pk'
    query_pk_and_slug = False
    """
    model = None
    queryset = None
    slug_field = 'slug'
    context_object_name = None
    slug_url_kwarg = 'slug'
    pk_url_kwarg = 'pk'
    query_pk_and_slug = False

    def get_object(self, queryset=None):
        """
        返回要该视图要展示的对象

        需要 self.queryset 和 URL 里的 pk 或 slug 参数
        子类可重写此方法返回任何对象
        """
        # 使用定制的 queryset
        if queryset is None:
            queryset = self.get_queryset()

        # 尝试用主键查询
        pk = self.kwargs.get(self.pk_url_kwarg)
        slug = self.kwargs.get(self.slug_url_kwarg)
        if pk is not None:
            queryset = queryset.filter(pk=pk)

        # 然后用 slug 查询仅在 pk 为空 或是双重查询情况下
        if slug is not None and (pk is None or self.query_pk_and_slug):
            slug_field = self.get_slug_field()
            ## **{slug_field: slug} **可以解包字典
            queryset = queryset.filter(**{slug_field: slug})

        # 如果 pk 和 slug 都没有，就是错误
        if pk is None and slug is None:
            raise AttributeError(
                "Generic detail view %s must be called with either an object "
                "pk or a slug in the URLconf." % self.__class__.__name__
            )

        try:
            # 从过滤后的 queryset 获取该对象一定只有一个
            obj = queryset.get()
        except queryset.model.DoesNotExist:
            # 要么就不存在
            raise Http404(_("No %(verbose_name)s found matching the query") %
                          {'verbose_name': queryset.model._meta.verbose_name})
        return obj

    def get_queryset(self):
        """
        返回用来获取对象的查询集

        get_object() 重写之后这个就不会调用.
        """
        if self.queryset is None:
            if self.model:
                return self.model._default_manager.all()
            else:
                raise ImproperlyConfigured(
                    "%(cls)s is missing a QuerySet. Define "
                    "%(cls)s.model, %(cls)s.queryset, or override "
                    "%(cls)s.get_queryset()." % {
                        'cls': self.__class__.__name__
                    }
                )
        return self.queryset.all()

    def get_slug_field(self):
        """获取用来查询的slug字段名称"""
        return self.slug_field

    def get_context_object_name(self, obj):
        """获取上下文中对象用名."""
        if self.context_object_name:
            return self.context_object_name
        elif isinstance(obj, models.Model):
            ## 默认模型名
            return obj._meta.model_name
        else:
            return None

    def get_context_data(self, **kwargs):
        """把单个对象放进上下文字典."""
        context = {}
        if self.object:
            ## object 和 model_name 指向同一个对象 双保险
            context['object'] = self.object
            context_object_name = self.get_context_object_name(self.object)
            if context_object_name:
                context[context_object_name] = self.object
        ## 若是重写 get_context_data 也应该如此结尾
        context.update(kwargs)
        return super().get_context_data(**context)


class BaseDetailView(SingleObjectMixin, View):
    """展示单个对象的基本视图"""
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class SingleObjectTemplateResponseMixin(TemplateResponseMixin):
    """
    单个对象的模板视图mixin

    template_name_field = None
    template_name_suffix = '_detail'
    """
    template_name_field = None
    template_name_suffix = '_detail'

    def get_template_names(self):
        """
        返回模板名列表。若 render_to_response 被重写，此方法将不会调用。
        列表里面可能有：
        * template_name
        * template_name_field 
        * <app_label>/<model_name><template_name_suffix>.html
        """
        try:
            names = super().get_template_names()
        except ImproperlyConfigured:
            # 从空列表开始
            names = []

            # 如果 self.template_name_field 设置了
            # 将此对象该字段的值作为模板名 太不常用
            if self.object and self.template_name_field:
                name = getattr(self.object, self.template_name_field, None)
                if name:
                    names.insert(0, name)

            # 默认的是 <app>/<model>_detail.html;
            # 如果展示对象是个 model.
            if isinstance(self.object, models.Model):
                object_meta = self.object._meta
                names.append("%s/%s%s.html" % (
                    object_meta.app_label,
                    object_meta.model_name,
                    self.template_name_suffix
                ))
            elif getattr(self, 'model', None) is not None and issubclass(self.model, models.Model):
                names.append("%s/%s%s.html" % (
                    self.model._meta.app_label,
                    self.model._meta.model_name,
                    self.template_name_suffix
                ))

            # 如果还是每有找到模板名
            # 向上抛出错误
            if not names:
                raise

        return names


class DetailView(SingleObjectTemplateResponseMixin, BaseDetailView):
    """
    渲染单个对象的细节视图
    
    默认是从 self.queryset 里面查询
    但是可以重写 self.get_object() 返回任何对象。
    """
