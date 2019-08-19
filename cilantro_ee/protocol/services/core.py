import asyncio
import json


class SocketEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, SocketStruct):
            return str(o)
        return json.JSONEncoder.default(self, o)


class SocketStruct:
    def __init__(self, protocol: int, id: str, port: int=0):
        self.protocol = protocol
        self.id = id

        if protocol == Protocols.INPROC:
            port = 0
        self.port = port

    def zmq_url(self):
        if not self.port:
            return '{}{}'.format(Protocols.PROTOCOL_STRINGS[self.protocol], self.id)
        else:
            return '{}{}:{}'.format(Protocols.PROTOCOL_STRINGS[self.protocol], self.id, self.port)

    def __str__(self):
        return self.zmq_url()

    @classmethod
    def from_string(cls, str):
        protocol = Protocols.TCP

        for protocol_string in Protocols.PROTOCOL_STRINGS:
            if len(str.split(protocol_string)) > 1:
                protocol = Protocols.PROTOCOL_STRINGS.index(protocol_string)
                str = str.split(protocol_string)[1]

        if protocol != Protocols.INPROC:
            _id, port = str.split(':')
            port = int(port)

            return cls(protocol=protocol, id=_id, port=port)
        else:
            return cls(protocol=protocol, id=str, port=None)

    @classmethod
    def is_valid(cls, s):
        return ':' in s


class Protocols:
    TCP = 0
    INPROC = 1
    ICP = 2
    PROTOCOL_STRINGS = ['tcp://', 'inproc://', 'icp://']


def sockstr(s: str):
    return SocketStruct.from_string(s)


async def defer():
    await asyncio.sleep(0)