from enum import StrEnum
from .secrets import TEST_USERNAME, TEST_PASSWORD

TEST_FRAMEWORK_ASYNC = 'async'
TEST_FRAMEWORK_SYNC = 'sync'

PERSISTED_INFO_PATH = ".persisted_info.json"
TEST_FLAGS = {
    "IGNORE_RATE_LIMIT": True,
}