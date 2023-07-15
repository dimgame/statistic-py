#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# MIT License
#
# Copyright (c) 2019 Albert Moky
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ==============================================================================

"""
    Service Bot
    ~~~~~~~~~~~
    Bot for statistics

    Data format:

        "users_log-{yyyy}-{mm}-{dd}.js"

            {
                "yyyy-mm-dd HH:MM": [
                    "ID1",
                    "ID2"
                ]
            }

        "stats_log-{yyyy}-{mm}-{dd}.js"

            {
                "yyyy-mm-dd HH:MM": [
                    {
                        "S": 0,
                        "T": 1,
                        "C": 2
                    }
                ]
            }

        "speeds_log-{yyyy}-{mm}-{dd}.js"

            {
                "yyyy-mm-dd HH:MM": [
                    {
                        "provider"     : "provider_id",
                        "station"      : "host:port",
                        "client"       : "host:port",
                        "response_time": 0.125
                    }
                ]
            }

    Fields:
        'S' - Sender type
        'C' - Counter
        'U' - User ID (reserved)
        'T' - message Type

    Sender type:
        https://github.com/dimchat/mkm-py/blob/master/mkm/protocol/network.py

    Message type:
        https://github.com/dimchat/dkd-py/blob/master/dkd/protocol/types.py
"""

import threading
import time
from typing import Optional, Union, Tuple, List, Dict

from dimples import ID, ReliableMessage
from dimples import ContentType, Content
from dimples import TextContent, CustomizedContent
from dimples import ContentProcessor, ContentProcessorCreator
from dimples import BaseContentProcessor
from dimples import CustomizedContentProcessor
from dimples import Facebook
from dimples import Config
from dimples.utils import Singleton, Log, Logging
from dimples.utils import Path, Runner
from dimples.database.dos import Storage
from dimples.client import ClientMessageProcessor
from dimples.client import ClientContentProcessorCreator

path = Path.abs(path=__file__)
path = Path.dir(path=path)
path = Path.dir(path=path)
Path.add(path=path)

from libs.client import Checkpoint
from bots.shared import GlobalVariable, start_bot


def get_name(identifier: ID, facebook: Facebook) -> str:
    doc = facebook.document(identifier=identifier)
    if doc is not None:
        name = doc.name
        if name is not None and len(name) > 0:
            return name
    name = identifier.name
    if name is not None and len(name) > 0:
        return name
    return str(identifier.address)


def two_digits(value: int) -> str:
    if value < 10:
        return '0%s' % value
    else:
        return '%s' % value


def parse_time(msg_time: float) -> Tuple[str, str, str, str, str]:
    local_time = time.localtime(msg_time)
    assert isinstance(local_time, time.struct_time), 'time error: %s' % local_time
    year = str(local_time.tm_year)
    month = two_digits(value=local_time.tm_mon)
    day = two_digits(value=local_time.tm_mday)
    hours = two_digits(value=local_time.tm_hour)
    minutes = two_digits(value=local_time.tm_min)
    return year, month, day, hours, minutes


@Singleton
class StatRecorder(Runner, Logging):

    def __init__(self):
        super().__init__()
        self.__lock = threading.Lock()
        self.__contents: List[CustomizedContent] = []
        self.__config: Config = None

    def _get_path(self, option: str, msg_time: float) -> str:
        temp = self.__config.get_string(section='statistic', option=option)
        assert temp is not None, 'failed to get users_log: %s' % self.__config
        year, month, day, _, _ = parse_time(msg_time=msg_time)
        return temp.replace('{yyyy}', year).replace('{mm}', month).replace('{dd}', day)

    def add_log(self, content: CustomizedContent):
        with self.__lock:
            self.__contents.append(content)

    def _next(self) -> Optional[CustomizedContent]:
        with self.__lock:
            if len(self.__contents) > 0:
                return self.__contents.pop(0)

    def _save_users(self, msg_time: float, users: List[str]):
        log_path = self._get_path(msg_time=msg_time, option='users_log')
        container = Storage.read_json(path=log_path)
        if container is None:
            container = {}
        year, month, day, hours, minutes = parse_time(msg_time=msg_time)
        log_tag = '%s-%s-%s %s:%s' % (year, month, day, hours, minutes)
        array = container.get(log_tag)
        if array is None:
            array = []
            container[log_tag] = array
        # append users
        for item in users:
            array.append(item)
        return Storage.write_json(container=container, path=log_path)

    def _save_stats(self, msg_time: float, stats: List[Dict]):
        log_path = self._get_path(msg_time=msg_time, option='stats_log')
        container = Storage.read_json(path=log_path)
        if container is None:
            container = {}
        year, month, day, hours, minutes = parse_time(msg_time=msg_time)
        log_tag = '%s-%s-%s %s:%s' % (year, month, day, hours, minutes)
        array = container.get(log_tag)
        if array is None:
            array = []
            container[log_tag] = array
        # append records
        for item in stats:
            array.append(item)
        return Storage.write_json(container=container, path=log_path)

    def _save_speeds(self, msg_time: float, provider: str, stations: List[Dict], client: str):
        log_path = self._get_path(msg_time=msg_time, option='speeds_log')
        container = Storage.read_json(path=log_path)
        if container is None:
            container = {}
        year, month, day, hours, minutes = parse_time(msg_time=msg_time)
        log_tag = '%s-%s-%s %s:%s' % (year, month, day, hours, minutes)
        array = container.get(log_tag)
        if array is None:
            array = []
            container[log_tag] = array
        # append speeds
        for srv in stations:
            host = srv.get('host')
            port = srv.get('port')
            response_time = srv.get('response_time')
            item = {
                'provider': provider,
                'station': '%s:%d' % (host, port),
                'client': client,
                'response_time': response_time,

            }
            array.append(item)
        return Storage.write_json(container=container, path=log_path)

    # Override
    def process(self) -> bool:
        content = self._next()
        if content is None:
            # nothing to do now, return False to have a rest
            return False
        now = time.time()
        msg_time = content.time
        if msg_time is None or msg_time < now - 3600*24*7:
            self.warning(msg='message expired: %s' % content)
            return True
        try:
            mod = content.module
            if mod == 'users':
                users = content.get('users')
                self._save_users(msg_time=msg_time, users=users)
            elif mod == 'stats':
                stats = content.get('stats')
                self._save_stats(msg_time=msg_time, stats=stats)
            elif mod == 'speeds':
                provider = content.get('provider')
                stations = content.get('stations')
                client = content.get('remote_address')
                if isinstance(client, List):  # or isinstance(client, Tuple):
                    assert len(client) == 2, 'socket address error: %s' % client
                    client = '%s:%d' % (client[0], client[1])
                self._save_speeds(msg_time=msg_time, provider=provider, stations=stations, client=client)
            else:
                self.warning(msg='ignore mod: %s, %s' % (mod, content))
        except Exception as e:
            self.error(msg='failed to process content: %s, %s' % (e, content))
        return True

    def start(self, config: Config):
        self.__config = config
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()


class TextContentProcessor(BaseContentProcessor, Logging):
    """ Process text message content """

    # Override
    def process(self, content: Content, msg: ReliableMessage) -> List[Content]:
        assert isinstance(content, TextContent), 'text content error: %s' % content
        text = content.text
        sender = msg.sender
        if g_checkpoint.duplicated(msg=msg):
            self.warning(msg='duplicated content from %s: %s' % (sender, text))
            return []
        nickname = get_name(identifier=sender, facebook=self.facebook)
        self.info(msg='received text message from %s: "%s"' % (nickname, text))
        # TODO: parse text for your business
        return []


class StatContentProcessor(CustomizedContentProcessor, Logging):
    """ Process customized stat content """

    # Override
    def process(self, content: Content, msg: ReliableMessage) -> List[Content]:
        assert isinstance(content, CustomizedContent), 'stat content error: %s' % content
        app = content.application
        mod = content.module
        act = content.action
        sender = msg.sender
        if g_checkpoint.duplicated(msg=msg):
            self.warning(msg='duplicated content from %s: %s, %s, %s' % (sender, app, mod, act))
            return []
        self.debug(msg='received content from %s: %s, %s, %s' % (sender, app, mod, act))
        return super().process(content=content, msg=msg)

    # Override
    def _filter(self, app: str, content: CustomizedContent, msg: ReliableMessage) -> Optional[List[Content]]:
        if app == 'chat.dim.monitor':
            # app ID matched
            return None
        # unknown app ID
        return super()._filter(app=app, content=content, msg=msg)

    # Override
    def handle_action(self, act: str, sender: ID, content: CustomizedContent, msg: ReliableMessage) -> List[Content]:
        recorder = StatRecorder()
        mod = content.module
        if mod == 'users':
            users = content.get('users')
            self.info(msg='received station log [users]: %s' % users)
            recorder.add_log(content=content)
        elif mod == 'stats':
            stats = content.get('stats')
            self.info(msg='received station log [stats]: %s' % stats)
            recorder.add_log(content=content)
        elif mod == 'speeds':
            provider = content.get('provider')
            stations = content.get('stations')
            remote_address = content.get('remote_address')
            self.info(msg='received client log [speeds]: %s => %s, %s' % (remote_address, provider, stations))
            recorder.add_log(content=content)
        else:
            self.error(msg='unknown module: %s, action: %s, %s' % (mod, act, content))
        # respond nothing
        return []


class BotContentProcessorCreator(ClientContentProcessorCreator):

    # Override
    def create_content_processor(self, msg_type: Union[int, ContentType]) -> Optional[ContentProcessor]:
        # text
        if msg_type == ContentType.TEXT:
            return TextContentProcessor(facebook=self.facebook, messenger=self.messenger)
        # application customized
        if msg_type == ContentType.CUSTOMIZED:
            return StatContentProcessor(facebook=self.facebook, messenger=self.messenger)
        # others
        return super().create_content_processor(msg_type=msg_type)


class BotMessageProcessor(ClientMessageProcessor):

    # Override
    def _create_creator(self) -> ContentProcessorCreator:
        return BotContentProcessorCreator(facebook=self.facebook, messenger=self.messenger)


g_checkpoint = Checkpoint()
g_recorder = StatRecorder()


#
# show logs
#
Log.LEVEL = Log.DEVELOP


DEFAULT_CONFIG = '/etc/dim/config.ini'


if __name__ == '__main__':
    start_bot(default_config=DEFAULT_CONFIG,
              app_name='ServiceBot: Statistics',
              ans_name='statistic',
              processor_class=BotMessageProcessor)
    shared = GlobalVariable()
    g_recorder.start(config=shared.config)
