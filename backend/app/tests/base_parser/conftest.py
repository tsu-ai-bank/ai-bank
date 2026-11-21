import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from parsers.base_parser import BaseParser

@pytest.fixture
def parser():
    return BaseParser(url="http://example.invalid", organization="test")