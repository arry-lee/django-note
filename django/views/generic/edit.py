"""
Last-View：2019年8月9日08:10:03
View-Counter：1
"""
from django.core.exceptions import ImproperlyConfigured
from django.forms import models as model_forms
from django.http import HttpResponseRedirect
from django.views.generic.base import ContextMixin, TemplateResponseMixin, View
from django.views.generic.detail import (
    BaseDetailView, SingleObjectMixin, SingleObjectTemplateResponseMixin,
)


class FormMixin(ContextMixin):
    """提供里一个处理表单的mixin"""
    initial = {}
    form_class = None
    success_url = None
    prefix = None

    def get_initial(self):
        """返回初始化表单数据的一个拷贝"""
        return self.initial.copy()

    def get_prefix(self):
        """返回这个表单的前缀"""
        ## 前缀在表单里面的位置和作用是什么？
        return self.prefix

    def get_form_class(self):
        """返回这个表单的类"""
        return self.form_class

    def get_form(self, form_class=None):
        """获取这个视图所用表单的实例"""
        if form_class is None:
            form_class = self.get_form_class()
        return form_class(**self.get_form_kwargs())

    def get_form_kwargs(self):
        """返回实例化表单的关键字参数"""
        kwargs = {
            'initial': self.get_initial(),
            'prefix': self.get_prefix(),
        }

        if self.request.method in ('POST', 'PUT'):
            kwargs.update({
                'data': self.request.POST,
                'files': self.request.FILES,
            })
        return kwargs

    def get_success_url(self):
        """提交表单合法之后的重定向必须有"""
        if not self.success_url:
            raise ImproperlyConfigured("No URL to redirect to. Provide a success_url.")
        return str(self.success_url)  # success_url may be lazy

    def form_valid(self, form):
        """如果表单验证通过 重定向到成功页面"""
        # 这里必须重写
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        """表单验证不合法 则返回该表单"""
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        """把表单放进上下文"""
        if 'form' not in kwargs:
            kwargs['form'] = self.get_form()
        return super().get_context_data(**kwargs)


class ModelFormMixin(FormMixin, SingleObjectMixin):
    """提供一个展示和处理模型表单的mixin"""
    fields = None # 展示字段

    def get_form_class(self):
        """返回用在视图里的表单类"""
        # fields 和 form_class 不能同时使用
        if self.fields is not None and self.form_class:
            raise ImproperlyConfigured(
                "Specifying both 'fields' and 'form_class' is not permitted."
            )
        if self.form_class:
            return self.form_class
        else:
            if self.model is not None:
                # 如果显式提供了 model 使用之
                model = self.model
            elif getattr(self, 'object', None) is not None:
                # 如果该视图操作单例对象，用它的类
                model = self.object.__class__
            else:
                # 获取查询集的模型类
                model = self.get_queryset().model

            if self.fields is None:
                raise ImproperlyConfigured(
                    "Using ModelFormMixin (base class of %s) without "
                    "the 'fields' attribute is prohibited." % self.__class__.__name__
                )
            # 使用model_forms 的工厂函数生成模型表单类
            return model_forms.modelform_factory(model, fields=self.fields)

    def get_form_kwargs(self):
        """返回实例化表单是关键字参数"""
        kwargs = super().get_form_kwargs()
        if hasattr(self, 'object'):
            # 上下文里的 instance 源自此处
            kwargs.update({'instance': self.object})
        return kwargs

    def get_success_url(self):
        """处理完成之后的重定向"""
        if self.success_url:
            # url 的 format 方法能做什么？
            url = self.success_url.format(**self.object.__dict__)
        else:
            try:
                ## 模型提供了 get_absolute_url 的话会很方便
                url = self.object.get_absolute_url()
            except AttributeError:
                raise ImproperlyConfigured(
                    "No URL to redirect to.  Either provide a url or define"
                    " a get_absolute_url method on the Model.")
        return url

    def form_valid(self, form):
        """表单验证提供.直接保存表单创建模型实例"""
        self.object = form.save()
        # 顶层最终是要回到 success url 的
        return super().form_valid(form)


class ProcessFormView(View):
    """GET 渲染 POST 处理"""
    def get(self, request, *args, **kwargs):
        """GET 返回空白表单"""
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        """
        通过POST的数据实例化表单，然后验证
        """
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    # PUT is a valid HTTP verb for creating (with a known URL) or editing an
    # object, note that browsers only support POST for now.
    def put(self, *args, **kwargs):
        return self.post(*args, **kwargs)


class BaseFormView(FormMixin, ProcessFormView):
    """展示表单的基类"""


class FormView(TemplateResponseMixin, BaseFormView):
    """用模板展示表单的基类"""


class BaseCreateView(ModelFormMixin, ProcessFormView):
    """
    创建一个实例对象的基类视图

    需要继承并提供一个响应response的混类.
    """
    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = None
        return super().post(request, *args, **kwargs)


class CreateView(SingleObjectTemplateResponseMixin, BaseCreateView):
    """
    创建一个对象，使用一个渲染的模板相应
    View for creating a new object, with a response rendered by a template.
    """
    template_name_suffix = '_form'


class BaseUpdateView(ModelFormMixin, ProcessFormView):
    """
    Base view for updating an existing object.

    Using this base class requires subclassing to provide a response mixin.
    """
    def get(self, request, *args, **kwargs):
        # get_object 需要被基类实现
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)


class UpdateView(SingleObjectTemplateResponseMixin, BaseUpdateView):
    """View for updating an object, with a response rendered by a template."""
    template_name_suffix = '_form'


class DeletionMixin:
    """提供删除对象的能力视图"""
    success_url = None

    def delete(self, request, *args, **kwargs):
        """
        找到对象删除之，返回删除成功的 url
        """
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.delete()
        return HttpResponseRedirect(success_url)

    # Add support for browsers which only accept GET and POST for now.
    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)

    def get_success_url(self):
        if self.success_url:
            return self.success_url.format(**self.object.__dict__)
        else:
            raise ImproperlyConfigured(
                "No URL to redirect to. Provide a success_url.")


class BaseDeleteView(DeletionMixin, BaseDetailView):
    """
    Base view for deleting an object.

    Using this base class requires subclassing to provide a response mixin.
    """


class DeleteView(SingleObjectTemplateResponseMixin, BaseDeleteView):
    """
    还要返回一个确认删除的页面
    View for deleting an object retrieved with self.get_object(), with a
    response rendered by a template.
    """
    template_name_suffix = '_confirm_delete'
