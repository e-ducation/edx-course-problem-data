import logging
from collections import deque

from opaque_keys.edx.keys import CourseKey, UsageKey
from opaque_keys.edx.locator import BlockUsageLocator, InvalidKeyError
from xmodule.modulestore.django import modulestore
from bson.objectid import ObjectId
from bson.errors import InvalidId
from xmodule.modulestore.split_mongo.split_draft import DraftVersioningModuleStore
from xmodule.modulestore.split_mongo import BlockKey, CourseEnvelope

from .exceptions import GetItemError

log = logging.getLogger("mongo.api")


class BlockStructure(object):

    def __init__(self, block_id_string, version_guid=''):
        self.block_id_string = block_id_string
        self.version_guid = version_guid
        self.usage_key = None
        self.xblock = None
        self.xblocks = None

        self._get_usage_key()
        self._get_xblock()

    def _get_usage_key(self):
        try:
            block_id = 'block-v1:' + self.block_id_string
            self.usage_key = UsageKey.from_string(block_id)
        except InvalidKeyError:
            course_key = CourseKey.from_string(self.block_id_string)
            pattern = u"{course_key}+{BLOCK_TYPE_PREFIX}@{block_type}+{BLOCK_PREFIX}@{block_id}"
            block_id = pattern.format(
                course_key=course_key._to_string(),
                BLOCK_TYPE_PREFIX=course_key.BLOCK_TYPE_PREFIX,
                block_type='course',
                BLOCK_PREFIX=course_key.BLOCK_PREFIX,
                block_id='course'
            )
            self.usage_key = BlockUsageLocator._from_string(block_id)
        except:
            self.usage_key = None

    def _get_xblock(self):
        try:
            version_guid = ObjectId(self.version_guid)
            self.version_guid = version_guid
        except InvalidId:
            version_guid = None

        if version_guid is not None:
            self._get_version_xblock()
        else:
            store = modulestore()
            with store.bulk_operations(self.usage_key.course_key):
                try:
                    self.xblock = store.get_item(self.usage_key, depth=None)
                except Exception:
                    raise GetItemError

    def _get_version_xblock(self):

        course_key = self.usage_key.course_key
        block_key = BlockKey.from_usage_key(self.usage_key)

        store = modulestore()

        for s in store.modulestores:
            if isinstance(s, DraftVersioningModuleStore):
                try:
                    entry = s.get_structure(course_key, self.version_guid)
                    course = CourseEnvelope(course_key.replace(version_guid=self.version_guid), entry)

                    course_entry = course
                    runtime = s._get_cache(course_entry.structure['_id'])

                    if runtime is None:
                        runtime = s.create_runtime(course_entry, lazy=True)

                    item = runtime.load_item(block_key, course_entry)

                    self.xblock = item
                except Exception:
                    raise GetItemError

    def get_xblocks(self):
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

        return self.xblocks if self.xblocks is not None else []
