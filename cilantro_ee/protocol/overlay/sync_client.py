from cilantro_ee.protocol.overlay.client import OverlayClient
from math import ceil

import time
import asyncio

class OverlayClientSync(OverlayClient):
    def __init__(self, ctx):
        super().__init__(self._handle_overlay_reply, self._handle_overlay_reply, ctx=ctx)
        self.timeout = 5         # secs
        self.sleep_time = 0.2    # secs
     
        self.timeout_iter = ceil(self.timeout / self.sleep_time)

        self.events = {}

    def _handle_overlay_reply(self, e):
        self.log.debugv("raghu OverlayClientSync got overlay reply {}".format(e))

        if 'event_id' in e:
            self.events[e['event_id']] = e

        else:
            self.log.debugv("OverlayClientSync got overlay response {} that has no event_id associated. "
                            "Ignoring.".format(e['event']))

    async def async_get_ip_sync(self, vk):
        event_id = self.get_ip_from_vk(vk)
        iter = 0
        while (iter < self.timeout_iter) and (event_id not in self.events):
            await asyncio.sleep(self.sleep_time)
            iter += 1
        e = self.events.pop(event_id, None)
        if e and e['event'] == 'got_ip':
            return e['ip']
        return None
