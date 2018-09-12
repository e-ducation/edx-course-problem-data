# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import logging

from django.utils.translation import ugettext as _
from lxml import etree
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.lib.api.authentication import OAuth2AuthenticationAllowInactiveUser
from opaque_keys.edx.locator import InvalidKeyError

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from xmodule.modulestore.split_mongo.caching_descriptor_system import ItemNotFoundError
from xmodule.modulestore.mongo.draft import DraftModuleStore

import util_code
from .models import BlockStructure
from .pagination import BlockNumberPagination
from .exceptions import NotSupportType

log = logging.getLogger("exam.api")


class ProblemParser(object):

    def __init__(self, xblock):

        self.id = xblock.scope_ids.usage_id._to_string()
        self.xblock = xblock
        self.tree = etree.XML(xblock.data)
        self.type = ProblemParser.parse_type(xblock.problem_types)

    def _get_title(self, tree, problem):
        label = problem.find("label")
        p = tree.find("p")

        if label is not None:
            title = label.text
            return title
        if p is not None:
            title = p.text
            return title

        return ""

    def get_content(self):
        # choice problem have options, answers, hints, feedbacks attributes
        # stringresponse problem have answers, optionanswers, hints, feedbacks attributes
        tree = self.tree
        if self.type in ["multiplechoiceresponse", "choiceresponse"]:
            problem = tree.find(self.type)
            title = self._get_title(tree, problem)
            choices = self.get_choices(problem)
            options = [item.text for item in choices]
            corrects = filter(lambda x: x.attrib['correct'] == 'true', choices)
            answers = [choices.index(item) for item in corrects]

            data = {
                "id": self.id,
                "type": self.type,
                "title": title,
                "options": options,
                "answers": answers,
            }
        elif self.type in ["numericalresponse", "stringresponse"]:
            problem = tree.find(self.type)
            title = self._get_title(tree, problem)
            answers = problem.attrib['answer']
            addition = problem.find("additional_answer")

            data = {
                "id": self.id,
                "type": self.type,
                "title": title,
                "answers": answers,
            }
            if addition is not None:
                additional_answer = addition.attrib['answer']
                data.update({"additional_answer": additional_answer})
        else:
            log.error(self.type)
            raise NotSupportType

        return data

    def get_choices(self, problem):
        if self.type == "multiplechoiceresponse":
            choices = problem.find("choicegroup").findall("choice")
        elif self.type == "choiceresponse":
            choices = problem.find("checkboxgroup").findall("choice")

        return choices

    @staticmethod
    def parse_type(type):
        if len(type) == 1:
            return list(type)[0]
        elif len(type) > 1:
            return type
        else:
            return None

    @staticmethod
    def has_multi_problem(problem):
        tree = etree.XML(problem.data)
        ptype = ProblemParser.parse_type(problem.problem_types)
        occurs = tree.findall(ptype)
        if len(occurs) > 1:
            return True
        else:
            return False


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


class ProblemView(APIView):
    """
    - 题目列表接口
    * 分页，单页 10 条记录
    * 排序，按创建时间，降序排序
    * 搜索，按「题目内容」，模糊搜索
    * 筛选，课程、章节、题型
    """

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
        return data

    def get(self, request, *args, **kwargs):

        block_id = request.query_params.get('block_id', None)
        problem_type = request.query_params.get('problem_type', None)
        search_text = request.query_params.get('text', None)

        try:
            structure = BlockStructure(block_id)
            xblocks = structure.xblocks
        except ItemNotFoundError as ex:
            log.error(ex)
            data = {
                'msg': _("Course id is invalid."),
                'code': util_code.COURSE_ID_INVALID
            }
            return Response(data, status=status.HTTP_200_OK)
        except TypeError as ex:
            log.error(ex)
            data = {
                'msg': _("Block id is required."),
                'code': util_code.BLOCK_ID_REQUIRED
            }
            return Response(data, status=status.HTTP_200_OK)

        # 按题型过滤
        # 只有题目才有 problem_types
        if problem_type is not None:
            s = set()
            s.add(problem_type)
            xblocks = filter(lambda x: hasattr(x, 'problem_types')
                                       and x.problem_types == s, xblocks)

        # 允许展示的题目类型
        allowed_type = set(['stringresponse', 'multiplechoiceresponse', 'choiceresponse'])
        xblocks = filter(lambda x: hasattr(x, 'problem_types') and x.problem_types & allowed_type != set(), xblocks)

        # 只返回题目
        problems = filter(lambda x: x.scope_ids.block_type == 'problem', xblocks)

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
            represent = map(self.to_represent, page)
            return self.get_paginated_response(represent)
        else:
            represent = map(self.to_represent, problems)
            return Response(represent)


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
        xblocks = filter(lambda x: x.scope_ids.block_type ==
                                   'problem', xblocks)

        result = {}
        types_list = ["multiplechoiceresponse",
                      "choiceresponse", "stringresponse"]
        for ptype in types_list:
            s = set()
            s.add(ptype)

            filter_problems = filter(lambda x: hasattr(
                x, 'problem_types') and x.problem_types == s, xblocks)
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
        try:
            course_id = request.query_params.get('course_id', None)

            if course_id is None or course_id == u"":
                return Response()

            course = BlockStructure(course_id)
            xblocks = course.xblocks
            # each xblock has block_type
            results = filter(
                lambda x: x.scope_ids.block_type == "sequential", xblocks)
            results = filter(lambda x: hasattr(
                x, 'get_children') and x.get_children() != [], results)

            # filter no problem section
            results = filter(self.has_problem, results)

            chapters = map(self.to_represent, results)
            return Response(chapters)
        except InvalidKeyError as ex:
            data = {
                'msg': _("Course id is invalid."),
                'code': util_code.COURSE_ID_INVALID
            }
            return Response(data, status=status.HTTP_200_OK)
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
        xblocks = filter(lambda x: x.scope_ids.block_type ==
                                   'problem', xblocks)

        result = {}
        types_list = ["multiplechoiceresponse",
                      "choiceresponse", "stringresponse"]
        for ptype in types_list:
            s = set()
            s.add(ptype)

            filter_problems = filter(lambda x: hasattr(
                x, 'problem_types') and x.problem_types == s, xblocks)
            count = len(filter_problems)
            temp = {}
            temp[ptype] = count
            result.update(temp)

        # 名称 和 ID
        result.update({
            'id': structure.xblock.scope_ids.usage_id._to_string(),
            'name': structure.xblock.display_name,
        })

        return result

    def post(self, request, *args, **kwargs):
        section_id = request.data.get('section_id', None)

        if isinstance(section_id, list):
            result = map(self.count, section_id)
            return Response(result)
        else:
            data = {
                'msg': _("Section id is invalid."),
                'code': util_code.SECTION_ID_INVALID
            }
            return Response(data, status=status.HTTP_200_OK)


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

    def get_problem(self, types):

        def filter_types(section):
            structure = BlockStructure(section)
            xblocks = structure.xblocks
            xblocks = filter(
                lambda x: x.scope_ids.block_type == 'problem', xblocks)

            problems = dict()
            problems[section] = {}

            for ptype in types:
                s = set()
                s.add(ptype)

                def pattern(x): return hasattr(
                    x, 'problem_types') and x.problem_types == s

                result = filter(pattern, xblocks)
                id_list = [xblock.scope_ids.usage_id._to_string()
                           for xblock in result]

                data = {}
                data[ptype] = id_list
                problems[section].update(data)

            return problems

        return lambda x: filter_types(x)

    def post(self, request, *args, **kwargs):

        try:
            section_list = request.data.get('sections', [])
            types = request.data.get('types', [])

            results = map(self.get_problem(types), section_list)

            # output format transform
            data = {}
            for value in results:
                data[value.keys()[0]] = value.values()[0]

            return Response(data)

        except InvalidKeyError:
            data = {
                'msg': _("Problem id is invalid."),
                'code': util_code.PROBLEM_ID_INVALID
            }
            return Response(data, status=status.HTTP_200_OK)

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

        except ItemNotFoundError as ex:
            log.error(ex)
            data = {
                'msg': _("Invalid Block Key"),
                'code': util_code.BLOCK_KEY_INVALID
            }
            return Response(data, status=status.HTTP_200_OK)

        except InvalidKeyError:
            data = {
                'msg': _("Problem id is invalid."),
                'code': util_code.PROBLEM_ID_INVALID
            }
            return Response(data, status=status.HTTP_200_OK)

        except Exception as ex:
            log.error(ex)
            data = {
                'msg': _("Server Error")
            }
            return Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)