# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import logging

from django.contrib.auth import get_user_model
from django.utils.translation import ugettext as _
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.lib.api.authentication import OAuth2AuthenticationAllowInactiveUser

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin
from rest_framework import filters, status

from xmodule.modulestore.mongo.draft import DraftModuleStore

import util_code
from .models import BlockStructure
from .pagination import BlockNumberPagination
from .exceptions import GetItemError
from .parser import ProblemParser
from .serializers import UserSerializer


log = logging.getLogger("exam.api")


class CourseView(APIView):
    """
    - 课程列表接口
        * 搜索，按「课程标题」搜索
        * 权限，跟 CMS 保持一致
    """

    authentication_classes = (OAuth2AuthenticationAllowInactiveUser,)

    def to_represent(self, course):
        data = {
            'id': course.id.html_id(),
            'name': course.display_name
        }
        return data

    def get(self, request, *args, **kwargs):
        import datetime

        today = datetime.date.today()
        queryset = CourseOverview.objects.all().filter(start__lte=today, end__gte=today).order_by('display_name')

        title = request.query_params.get('title', None)
        if title is not None:
            queryset = queryset.filter(display_name__contains=title)

        represent = map(self.to_represent, queryset)
        return Response(represent, status=status.HTTP_200_OK)


class SectionView(APIView):
    """
    - 课程章节列表接口
        * 筛选，有题目的章节
    """

    authentication_classes = (OAuth2AuthenticationAllowInactiveUser,)

    def has_problem(self, xblock):
        structure = BlockStructure(xblock.scope_ids.usage_id._to_string())
        xblocks = structure.xblocks
        results = filter(lambda x: x.scope_ids.block_type == "problem", xblocks)

        return len(results) > 0

    def count(self, xblock_id):
        structure = BlockStructure(xblock_id)
        xblocks = structure.xblocks
        xblocks = filter(lambda x: x.scope_ids.block_type == 'problem', xblocks)

        result = {}
        types_list = ["multiplechoiceresponse", "choiceresponse", "stringresponse"]
        for ptype in types_list:
            s = set()
            s.add(ptype)

            filter_problems = filter(lambda x: hasattr(x, 'problem_types') and x.problem_types == s, xblocks)
            count = len(filter_problems)
            temp = {}
            temp[ptype] = count
            result.update(temp)

        return result

    def to_represent(self, xblock):
        xblock_id = xblock.scope_ids.usage_id._to_string()
        data = self.count(xblock_id)
        data.update({
            'id': xblock_id,
            'name': xblock.display_name,
        })
        return data

    def get(self, request, *args, **kwargs):

        course_id = request.query_params.get('course_id', None)

        try:
            course = BlockStructure(course_id)
            xblocks = course.xblocks

            # each xblock has block_type
            results = filter(lambda x: x.scope_ids.block_type == "sequential", xblocks)
            results = filter(lambda x: hasattr(x, 'get_children') and x.get_children() != [], results)

            # filter no problem section
            results = filter(self.has_problem, results)

            chapters = map(self.to_represent, results)
            return Response(chapters)

        except GetItemError as ex:
            data = {
                'msg': _("Course id is invalid."),
                'code': util_code.COURSE_ID_INVALID
            }
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        except Exception as ex:
            log.error(ex)
            data = {
                'msg': _("Server Error"),
            }
            return Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SectionCountView(APIView):
    """
    章节各题型的题目数量
    """

    authentication_classes = (OAuth2AuthenticationAllowInactiveUser,)

    def count(self, section_id):
        structure = BlockStructure(section_id)
        xblocks = structure.xblocks
        xblocks = filter(lambda x: x.scope_ids.block_type == 'problem', xblocks)

        result = {}
        types_list = ["multiplechoiceresponse", "choiceresponse", "stringresponse"]
        for ptype in types_list:
            s = set()
            s.add(ptype)

            filter_problems = filter(lambda x: hasattr(x, 'problem_types') and x.problem_types == s, xblocks)
            count = len(filter_problems)
            temp = {}
            temp[ptype] = count
            result.update(temp)

        result.update({
            'id': structure.xblock.scope_ids.usage_id._to_string(),
            'name': structure.xblock.display_name,
        })

        return result

    def post(self, request, *args, **kwargs):
        section_id = request.data.get('section_id', None)

        # 参数类型检查
        if not isinstance(section_id, list):
            data = {
                'msg': _("Section id is invalid."),
                'code': util_code.SECTION_ID_INVALID
            }
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = map(self.count, section_id)
            return Response(result)
        except GetItemError:
            data = {
                'msg': _("Section id is invalid."),
                'code': util_code.SECTION_ID_INVALID
            }
            return Response(data, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            data = {'msg': _("Server Error.")}
            return Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TypeView(APIView):
    """
    - 题目类型列表接口
    """

    authentication_classes = (OAuth2AuthenticationAllowInactiveUser,)

    def get(self, request):
        type_list = [
            _("multiplechoiceresponse"),
            _("choiceresponse"),
            _("stringresponse")
        ]

        return Response(type_list)


class SectionProblemView(APIView):
    """
    - 章节题目列表
    """

    authentication_classes = (OAuth2AuthenticationAllowInactiveUser,)

    def get_problem(self, section):

        structure = BlockStructure(section)
        xblocks = structure.xblocks
        xblocks = filter(
            lambda x: x.scope_ids.block_type == 'problem', xblocks)

        problems = dict()
        problems[section] = {}

        for ptype in self.types:
            s = set()
            s.add(ptype)

            result = filter(lambda x: hasattr(x, 'problem_types') and x.problem_types == s, xblocks)
            id_list = [xblock.scope_ids.usage_id._to_string() for xblock in result]

            data = {}
            data[ptype] = id_list
            problems[section].update(data)

        return problems

    def post(self, request, *args, **kwargs):

        section_list = request.data.get('sections', [])
        types = request.data.get('types', [])

        self.types = types

        try:
            results = map(self.get_problem, section_list)

            # output format transform
            data = {}
            for value in results:
                data[value.keys()[0]] = value.values()[0]

            return Response(data)

        except GetItemError:
            data = {
                'msg': _("Problem id is invalid."),
                'code': util_code.PROBLEM_ID_INVALID
            }
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        except Exception as ex:
            log.error(ex)
            data = {
                'msg': _("Server Error")
            }
            return Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DetailView(APIView):
    authentication_classes = (OAuth2AuthenticationAllowInactiveUser,)

    def get_content(self, problem):
        xblock = BlockStructure(problem).xblock
        data = ProblemParser(xblock).get_content()
        return data

    def post(self, request, *args, **kwargs):
        try:
            problem_list = request.data.get('problems', [])
            results = map(self.get_content, problem_list)
            return Response(results)

        except GetItemError as ex:
            log.error(ex)
            data = {
                'msg': _("Invalid Block Key"),
                'code': util_code.BLOCK_KEY_INVALID
            }
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        except Exception as ex:
            log.error(ex)
            data = {
                'msg': _("Server Error")
            }
            return Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProblemView(APIView):
    pagination_class = BlockNumberPagination

    authentication_classes = (OAuth2AuthenticationAllowInactiveUser,)

    @property
    def paginator(self):
        """
        The paginator instance associated with the view, or `None`.
        """
        if not hasattr(self, '_paginator'):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = self.pagination_class()
        return self._paginator

    def paginate_queryset(self, queryset):
        """
        Return a single page of results, or `None` if pagination is disabled.
        """
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        """
        Return a paginated style `Response` object for the given output data.
        """
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data)

    def get_problem_ids_by_search_text(self, text):
        from xmodule.modulestore.django import modulestore
        store = modulestore()
        for s in store.modulestores:
            if isinstance(s, DraftModuleStore):
                definition = s.database.modulestore.definitions
                problems = definition.find(
                    {
                        'fields.data': {"$regex": text},
                        'block_type': 'problem'
                    },
                    {'_id': 1}
                )
                return [problem['_id'] for problem in problems]
        return None

    def to_represent(self, xblock):
        data = ProblemParser(xblock).get_content()
        # for e in data:
        #     self.result.append(e)
        self.result.append(data)

    def get(self, request, *args, **kwargs):

        block_id = request.query_params.get('block_id', None)
        problem_type = request.query_params.get('problem_type', None)
        search_text = request.query_params.get('text', None)

        try:
            structure = BlockStructure(block_id)
            xblocks = structure.xblocks
        except GetItemError as ex:
            log.error(ex)
            data = {
                'msg': _("Block id is invalid."),
                'code': util_code.BLOCK_KEY_INVALID
            }
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        # 按题型过滤
        # 只有题目才有 problem_types
        if problem_type is not None:
            s = set()
            s.add(problem_type)
            xblocks = filter(lambda x: hasattr(x, 'problem_types')
                                       and x.problem_types == s, xblocks)

        # 允许展示的题目类型
        allowed_type = set(
            ['stringresponse', 'multiplechoiceresponse', 'choiceresponse'])
        xblocks = filter(lambda x: hasattr(x, 'problem_types')
                                   and x.problem_types & allowed_type != set(), xblocks)

        # 只返回题目
        problems = filter(lambda x: x.scope_ids.block_type ==
                                    'problem', xblocks)

        # 匹配 text
        if search_text is not None:
            search_problem_ids = self.get_problem_ids_by_search_text(
                search_text)
            if search_problem_ids is not None:
                problems = filter(
                    lambda x: x.scope_ids.def_id in search_problem_ids, problems)
            else:
                problems = []

        # 排序
        reversed(problems)

        # 过滤多重题目的xblock
        problems = filter(
            lambda x: ProblemParser.has_multi_problem(x) is False, problems)

        # 分页
        page = self.paginate_queryset(problems)
        if page is not None:
            self.result = []
            map(self.to_represent, page)
            return self.get_paginated_response(self.result)
        else:
            self.result = []
            map(self.to_represent, problems)
            return Response(self.result)


class UserViewSet(ListModelMixin, GenericViewSet):
    authentication_classes = (OAuth2AuthenticationAllowInactiveUser,)
    serializer_class = UserSerializer
    queryset = get_user_model().objects.all()
    filter_backends = (filters.SearchFilter,)
    search_fields = ('username', 'email')
