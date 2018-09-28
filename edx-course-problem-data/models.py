import logging
from collections import deque

from opaque_keys.edx.keys import CourseKey
from opaque_keys.edx.locator import BlockUsageLocator, InvalidKeyError
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.split_mongo.split_draft import DraftVersioningModuleStore
from xmodule.modulestore.split_mongo import BlockKey, CourseEnvelope

from .exceptions import GetItemError

log = logging.getLogger("mongo.api")


class BlockStructure(object):

    def __init__(self, block_id_string, definition_key=None):
        self.block_id_string = block_id_string
        self.block_id = None
        self.definition_key = definition_key
        self._transform_id()

        self.usage_key = None
        self.get_usage_key()

        self.xblock = None
        self.get_xblock()

        self.xblocks = None
        self.topological_traversal_BFS()

    def _transform_id(self):
        pattern = u"{course_key}+{BLOCK_TYPE_PREFIX}@{block_type}+{BLOCK_PREFIX}@{block_id}"

        try:
            course_key = CourseKey.from_string(self.block_id_string)
            self.block_id = pattern.format(
                course_key=course_key._to_string(),
                BLOCK_TYPE_PREFIX=course_key.BLOCK_TYPE_PREFIX,
                block_type='course',
                BLOCK_PREFIX=course_key.BLOCK_PREFIX,
                block_id='course'
            )
        except Exception as ex:
            self.block_id = self.block_id_string

    def get_usage_key(self):
        try:
            self.usage_key = BlockUsageLocator._from_string(self.block_id)
        except InvalidKeyError:
            self.usage_key = None

    def get_xblock(self):
        """
        usage_key is a BlockUsageLocator instance
        """
        usage_key = self.usage_key
        if usage_key is None:
            raise GetItemError

        store = modulestore()
        with store.bulk_operations(usage_key.course_key):
            try:
                self.xblock = store.get_item(usage_key, depth=None)
            except Exception:
                raise GetItemError

        if self.definition_key is not None:
            self.get_version_block()

    def topological_traversal_BFS(self):
        if self.xblocks is None:

            self.xblocks = []
            helperList = deque()

            if self.usage_key is not None:
                helperList.append(self.xblock)

            while len(helperList) > 0:
                tempElement = helperList.popleft()
                if tempElement is not None:
                    self.xblocks.append(tempElement)
                    if hasattr(tempElement, "get_children"):
                        helperList.extend(tempElement.get_children())
        else:
            pass

    def get_version_block(self):
        store = modulestore()

        markdown = None

        for s in store.modulestores:
            if isinstance(s, DraftVersioningModuleStore):
                entry = s.get_structure(self.usage_key.course_key, self.definition_key)
                envelope = CourseEnvelope(self.usage_key.replace(version_guid=self.definition_key), entry)

                block = s._get_block_from_structure(envelope.structure, BlockKey.from_usage_key(self.usage_key))
                markdown = block.markdown

        if markdown is not None:
            self.xblock.markdown = markdown
