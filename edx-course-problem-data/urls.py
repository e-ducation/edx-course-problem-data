from .views import (
    CourseView,
    ProblemView,
    SectionView,
    SectionCountView,
    TypeView,
    SectionProblemView,
    DetailView,
    UserViewSet,

)
from django.conf.urls import url
from rest_framework import routers

router = routers.SimpleRouter()

router.register(r'users', UserViewSet, 'users')
urlpatterns = [
    url(r'^courses$', CourseView.as_view()),
    url(r'^problems$', ProblemView.as_view()),
    url(r'^sections$', SectionView.as_view()),
    url(r'^sections/count$', SectionCountView.as_view()),
    url(r'^problem/types$', TypeView.as_view()),
    url(r'^section/problems$', SectionProblemView.as_view()),
    url(r'^problems/detail$', DetailView.as_view()),
]

urlpatterns += router.urls
