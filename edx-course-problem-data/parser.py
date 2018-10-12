# -*- coding: utf-8 -*-

import re
from lxml import etree

import capa.responsetypes as responsetypes
import capa.inputtypes as inputtypes
from django.utils.translation import ugettext as _
from xmodule.stringify import stringify_children
from collections import OrderedDict
import traceback

# extra things displayed after "show answers" is pressed
solution_tags = ['solution']

# fully accessible capa input types
ACCESSIBLE_CAPA_INPUT_TYPES = [
    'checkboxgroup',
    'radiogroup',
    'choicegroup',
    'optioninput',
    'textline',
    'formulaequationinput',
    'textbox',
]

# these get captured as student responses
response_properties = ["codeparam",
                       "responseparam", "answer", "openendedparam"]


class MultipleChoiceResponse(object):

    def __init__(self, xml, problem_data):
        self.xml = xml
        self.problem_data = problem_data
        self.setup_response()

    def setup_response(self):
        """
        Collects information from the XML for later use.

        correct_choices is a list of the correct choices.
        partial_choices is a list of the partially-correct choices.
        partial_values is a list of the scores that go with those
          choices, defaulting to 0.5 if no value is specified.
        """
        # call secondary setup for MultipleChoice questions, to set name
        # attributes
        self.mc_setup_response()

        # define correct choices (after calling secondary setup)
        xml = self.xml
        cxml = xml.xpath('//*[@id=$id]//choice', id=xml.get('id'))

        # contextualize correct attribute and then select ones for which
        # correct = "true"
        self.correct_choices = [
            cxml.index(choice)
            for choice in cxml
            if choice.get('correct').upper() == "TRUE"
        ]
        self.choices = [
            choice.text
            for choice in cxml
        ]

    def mc_setup_response(self):
        """
        Initialize name attributes in <choice> stanzas in the <choicegroup> in this response.
        Masks the choice names if applicable.
        """
        i = 0
        for response in self.xml.xpath("choicegroup"):
            # Is Masking enabled? -- check for shuffle or answer-pool features
            # Masking (self._has_mask) is off, to be re-enabled with a future PR.
            rtype = response.get('type')
            if rtype not in ["MultipleChoice"]:
                # force choicegroup to be MultipleChoice if not valid
                response.set("type", "MultipleChoice")
            for choice in list(response):
                # The regular, non-masked name:
                if choice.get("name") is not None:
                    name = "choice_" + choice.get("name")
                else:
                    name = "choice_" + str(i)
                    i += 1
                # If using the masked name, e.g. mask_0, save the regular name
                # to support unmasking later (for the logs).
                # Masking is currently disabled so this code is commented, as
                # the variable `mask_ids` is not defined. (the feature appears to not be fully implemented)
                # The original work for masking was done by Nick Parlante as part of the OLI Hinting feature.
                # if self.has_mask():
                #     mask_name = "mask_" + str(mask_ids.pop())
                #     self._mask_dict[mask_name] = name
                #     choice.set("name", mask_name)
                # else:
                choice.set("name", name)

    def get_answers(self):
        self.problem_data.update({
            'options': self.choices,
            'answers': self.correct_choices,
        })

        for solution in self.xml.xpath('//solution', id=self.xml.get('id')):
            answer = etree.tostring(solution, encoding='unicode', method='text')
            if answer:
                answer = answer.replace(' ', '').replace("\n", "").strip()
                self.problem_data.update({'solution': answer})
            else:
                self.problem_data.update({'solution': ''})

        title = self.problem_data.get('title', '')
        if title == '':
            for p in self.xml.xpath('//p'):
                if p.attrib.get('id') == self.xml.get('id'):
                    p_text = p.text
                    self.problem_data['title'] = p_text

        return self.problem_data


class ChoiceResponse(object):

    def __init__(self, xml, problem_data):
        self.xml = xml
        self.problem_data = problem_data
        self.setup_response()

    def get_choices(self):
        """Returns this response's XML choice elements."""
        return self.xml.xpath('//*[@id=$id]//choice', id=self.xml.get('id'))

    def assign_choice_names(self):
        """
        Initialize name attributes in <choice> tags for this response.
        """

        for index, choice in enumerate(self.get_choices()):
            choice.set("name", "choice_" + str(index))
            # If a choice does not have an id, assign 'A' 'B', .. used by CompoundHint
            if not choice.get('id'):
                choice.set("id", chr(ord("A") + index))

    def setup_response(self):
        self.assign_choice_names()

        self.correct_choices = []
        self.choices = []

        choices = self.get_choices()
        for choice in choices:
            correct = choice.get('correct').upper()

            # divide choices into correct and incorrect
            if correct == 'TRUE':
                index = choices.index(choice)
                self.correct_choices.append(index)

            self.choices.append(choice.text)

    def get_answers(self):
        self.problem_data.update({
            'options': self.choices,
            'answers': self.correct_choices,
        })

        for solution in self.xml.xpath('//solution', id=self.xml.get('id')):
            answer = etree.tostring(solution, encoding='unicode', method='text')
            if answer:
                answer = answer.replace(' ', '').replace("\n", "").strip()
                self.problem_data.update({'solution': answer})
            else:
                self.problem_data.update({'solution': ''})

        title = self.problem_data.get('title', '')
        if title == '':
            for p in self.xml.xpath('//p'):
                if p.attrib.get('id') == self.xml.get('id'):
                    p_text = p.text
                    self.problem_data['title'] = p_text

        return self.problem_data


class StringResponse(object):

    def __init__(self, xml, problem_data):
        self.xml = xml
        self.problem_data = problem_data
        self.setup_response()

    def setup_response_backward(self):
        self.correct_answer = [
            answer.strip() for answer in self.xml.get('answer').split('_or_')
        ]

    def setup_response(self):
        self.backward = '_or_' in self.xml.get('answer').lower()
        self.regexp = False
        self.case_insensitive = False
        if self.xml.get('type') is not None:
            self.regexp = 'regexp' in self.xml.get('type').lower().split(' ')
            self.case_insensitive = 'ci' in self.xml.get('type').lower().split(' ')

        # backward compatibility, can be removed in future, it is up to @Lyla Fisher.
        if self.backward:
            self.setup_response_backward()
            return
        # end of backward compatibility

        # XML compatibility note: in 2015, additional_answer switched to having a 'answer' attribute.
        # See make_xml_compatible in capa_problem which translates the old format.
        correct_answers = (
                [self.xml.get('answer')] +
                [element.get('answer') for element in self.xml.findall('additional_answer')]
        )
        self.correct_answer = [answer.strip() for answer in correct_answers]

    def get_answers(self):
        # Translators: Separator used in StringResponse to display multiple answers.
        # Example: "Answer: Answer_1 or Answer_2 or Answer_3".
        self.problem_data.update({
            'answers': self.correct_answer,
        })

        for solution in self.xml.xpath('//solution', id=self.xml.get('id')):
            answer = etree.tostring(solution, encoding='unicode', method='text')
            if answer:
                answer = answer.replace(' ', '').replace("\n", "").strip()
                self.problem_data.update({'solution': answer})
            else:
                self.problem_data.update({'solution': ''})

        title = self.problem_data.get('title', '')
        if title == '':
            for p in self.xml.xpath('//p'):
                if p.attrib.get('id') == self.xml.get('id'):
                    p_text = p.text
                    self.problem_data['title'] = p_text

        return self.problem_data


class ProblemParser(object):

    def __init__(self, xblock):
        self.xblock = xblock
        self.xblock_id = xblock.scope_ids.usage_id._to_string()
        self.problem_id = xblock.scope_ids.usage_id.block_id
        self.markdown = xblock.data
        self.problem_type = ProblemParser.parse_type(xblock.problem_types)

        # Convert startouttext and endouttext to proper <text></text>
        problem_text = xblock.data
        problem_text = re.sub(r"startouttext\s*/", "text", problem_text)
        problem_text = re.sub(r"endouttext\s*/", "/text", problem_text)
        self.problem_text = problem_text

        # parse problem XML file into an element tree
        self.tree = etree.XML(problem_text)

        self.make_xml_compatible(self.tree)

    def make_xml_compatible(self, tree):
        """
        Adjust tree xml in-place for compatibility before creating
        a problem from it.
        The idea here is to provide a central point for XML translation,
        for example, supporting an old XML format. At present, there just two translations.

        1. <additional_answer> compatibility translation:
        old:    <additional_answer>ANSWER</additional_answer>
        convert to
        new:    <additional_answer answer="ANSWER">OPTIONAL-HINT</addional_answer>

        2. <optioninput> compatibility translation:
        optioninput works like this internally:
            <optioninput options="('yellow','blue','green')" correct="blue" />
        With extended hints there is a new <option> tag, like this
            <option correct="True">blue <optionhint>sky color</optionhint> </option>
        This translation takes in the new format and synthesizes the old option= attribute
        so all downstream logic works unchanged with the new <option> tag format.
        """

        additionals = tree.xpath('//stringresponse/additional_answer')
        for additional in additionals:
            answer = additional.get('answer')
            text = additional.text
            if not answer and text:  # trigger of old->new conversion
                additional.set('answer', text)
                additional.text = ''

        for optioninput in tree.xpath('//optioninput'):
            correct_option = None
            child_options = []
            for option_element in optioninput.findall('./option'):
                option_name = option_element.text.strip()
                if option_element.get('correct').upper() == 'TRUE':
                    correct_option = option_name
                child_options.append("'" + option_name + "'")

            if len(child_options) > 0:
                options_string = '(' + ','.join(child_options) + ')'
                optioninput.attrib.update({'options': options_string})
                if correct_option:
                    optioninput.attrib.update({'correct': correct_option})

    def get_content(self):
        """
        标题
        描述
        选项
        答案
        可选答案
        提示
        """
        p_id = 1
        response_id = 1
        solution_id = 1
        problem = []
        tree = self.tree

        # 遍历 p 标签
        for ptag in tree.xpath('./p'):
            ptag_id = self.xblock_id + "_" + str(p_id)
            ptag.set('id', ptag_id)
            p_id += 1

        # 遍历 solution 标签
        for sol in tree.xpath('//solution'):
            sol_id = self.xblock_id + "_" + str(solution_id)
            sol.set('id', sol_id)
            solution_id += 1

        # 可能有多个小题
        questions = tree.xpath('//' + "|//".join(responsetypes.registry.registered_tags()))
        for response in questions:

            responsetype_id = self.xblock_id + "_" + str(response_id)
            # create and save ID for this response
            response.set('id', responsetype_id)
            response_id += 1

            # 题干
            answer_id = 1
            input_tags = inputtypes.registry.registered_tags()
            inputfields = tree.xpath(
                "|".join(['//' + response.tag + '[@id=$id]//' + x for x in input_tags]),
                id=responsetype_id
            )

            # 选项
            # assign one answer_id for each input type
            for entry in inputfields:
                entry.attrib['response_id'] = str(response_id)
                entry.attrib['answer_id'] = str(answer_id)
                entry.attrib['id'] = "%s_%i_%i" % (self.xblock_id, response_id, answer_id)
                answer_id = answer_id + 1

            # 找出标题
            problem_data = {}
            self.response_a11y_data(response, inputfields, responsetype_id, problem_data)

            # 实际解析
            data = self.get_content_by_type(response, problem_data, responsetype_id, questions)

            if data is not None:
                problem.append(data)

        if len(problem) > 1:
            return problem
        elif len(problem) == 1:
            return problem[0]
        else:
            return None

    def get_content_by_type(self, response, problem_data, responsetype_id, questions):
        # 按照题型获取不同的答案
        if self.problem_type == "multiplechoiceresponse":
            res = MultipleChoiceResponse(response, problem_data)
            data = res.get_answers()
            data.update({
                'id': responsetype_id if len(questions) > 1 else self.xblock_id,
                'type': self.problem_type,
                'version': str(self.xblock.definition_locator.definition_id)
            })

        elif self.problem_type == "choiceresponse":
            res = ChoiceResponse(response, problem_data)
            data = res.get_answers()
            data.update({
                'id': responsetype_id if len(questions) > 1 else self.xblock_id,
                'type': self.problem_type,
                'version': str(self.xblock.definition_locator.definition_id)
            })

        elif self.problem_type == "stringresponse":
            res = StringResponse(response, problem_data)
            data = res.get_answers()
            data.update({
                'id': responsetype_id if len(questions) > 1 else self.xblock_id,
                'type': self.problem_type,
                'version': str(self.xblock.definition_locator.definition_id)
            })

        # 过滤题型
        else:
            data = None

        return data

    def response_a11y_data(self, response, inputfields, responsetype_id, problem_data):
        """
        Construct data to be used for a11y.

        Arguments:
            response (object): xml response object
            inputfields (list): list of inputfields in a responsetype
            responsetype_id (str): responsetype id
            problem_data (dict): dict to be filled with response data
        """
        # if there are no inputtypes then don't do anything
        if not inputfields:
            return

        element_to_be_deleted = None
        label = ''

        if len(inputfields) > 1:
            response.set('multiple_inputtypes', 'true')
            group_label_tag = response.find('label')
            group_description_tags = response.findall('description')
            group_label_tag_id = u'multiinput-group-label-{}'.format(responsetype_id)
            group_label_tag_text = ''
            if group_label_tag is not None:
                group_label_tag.tag = 'p'
                group_label_tag.set('id', group_label_tag_id)
                group_label_tag.set('class', 'multi-inputs-group-label')
                group_label_tag_text = stringify_children(group_label_tag)
                response.set('multiinput-group-label-id', group_label_tag_id)

            group_description_ids = []
            for index, group_description_tag in enumerate(group_description_tags):
                group_description_tag_id = u'multiinput-group-description-{}-{}'.format(responsetype_id, index)
                group_description_tag.tag = 'p'
                group_description_tag.set('id', group_description_tag_id)
                group_description_tag.set('class', 'multi-inputs-group-description question-description')
                group_description_ids.append(group_description_tag_id)

            if group_description_ids:
                response.set('multiinput-group_description_ids', ' '.join(group_description_ids))

            for inputfield in inputfields:
                problem_data.update({
                    'group_label': group_label_tag_text,
                    'title': inputfield.attrib.get('label', ''),
                    'descriptions': {}
                })
        else:
            # Extract label value from <label> tag or label attribute from inside the responsetype
            responsetype_label_tag = response.find('label')
            if responsetype_label_tag is not None:
                label = stringify_children(responsetype_label_tag)
                # store <label> tag containing question text to delete
                # it later otherwise question will be rendered twice
                element_to_be_deleted = responsetype_label_tag
            elif 'label' in inputfields[0].attrib:
                # in this case we have old problems with label attribute and p tag having question in it
                # we will pick the first sibling of responsetype if its a p tag and match the text with
                # the label attribute text. if they are equal then we will use this text as question.
                # Get first <p> tag before responsetype, this <p> may contains the question text.
                p_tag = response.xpath('preceding-sibling::*[1][self::p]')

                if p_tag and p_tag[0].text == inputfields[0].attrib['label']:
                    label = stringify_children(p_tag[0])
                    element_to_be_deleted = p_tag[0]
            else:
                # In this case the problems don't have tag or label attribute inside the responsetype
                # so we will get the first preceding label tag w.r.t to this responsetype.
                # This will take care of those multi-question problems that are not using --- in their markdown.
                label_tag = response.xpath('preceding-sibling::*[1][self::label]')
                if label_tag:
                    label = stringify_children(label_tag[0])
                    element_to_be_deleted = label_tag[0]

            # delete label or p element only if inputtype is fully accessible
            if inputfields[0].tag in ACCESSIBLE_CAPA_INPUT_TYPES and element_to_be_deleted is not None:
                element_to_be_deleted.getparent().remove(element_to_be_deleted)

            # Extract descriptions and set unique id on each description tag
            description_tags = response.findall('description')
            description_id = 1
            descriptions = OrderedDict()
            for description in description_tags:
                descriptions = stringify_children(description)
                response.remove(description)
                description_id += 1

            problem_data.update({
                'title': label if label else '',
                'descriptions': descriptions
            })

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

        if isinstance(ptype, set):
            return True
        else:
            occurs = tree.findall(ptype)
            if len(occurs) > 1:
                return True
            else:
                return False
