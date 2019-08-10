from django.dispatch import Signal

request_started = Signal(providing_args=["environ"]) #请求开始
request_finished = Signal() #请求结束
got_request_exception = Signal(providing_args=["request"]) #捕获到异常
setting_changed = Signal(providing_args=["setting", "value", "enter"]) #设置被修改
