from .views import (
    CourseView,
    ProblemView,
    SectionView,
    SectionCountView,
    TypeView,
    SectionProblemView,
    DetailView,
)
from django.conf.urls import url

urlpatterns = [
    url(r'^courses$', CourseView.as_view()),
    url(r'^problems$', ProblemView.as_view()),
    url(r'^sections$', SectionView.as_view()),
    url(r'^sections/count$', SectionCountView.as_view()),
    url(r'^problem/types$', TypeView.as_view()),
    url(r'^section/problems$', SectionProblemView.as_view()),
    url(r'^problems/detail$', DetailView.as_view()),
]
