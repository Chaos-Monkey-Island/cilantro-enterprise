from cilantro_ee.protocol.comm import services
from cilantro_ee.storage.state import MetaDataStorage
from cilantro_ee.messages.message import MessageTypes


class BlockManager:
    def __init__(self):
        self.sbb_router = services.AsyncInbox()
        self.mn_publisher = None
        self.mn_subscription = services.SubscriptionService()
        self.public_router = None

        self.state = MetaDataStorage()

    async def start(self):
        pass

    async def handle_sub_msg(self):
        # Pull from the subscription message queue
        while True:
            if len(self.mn_subscription.received) > 0:
                msg = self.mn_subscription.received.pop(0)

                msg_filter, msg_type, msg_blob = msg

                # Process external ready signals
                if msg_type == MessageTypes.READY_EXTERNAL:
                    pass

                elif msg_type == MessageTypes.SKIP_BLOCK_NOTIFICATION or \
                        msg_type == MessageTypes.NEW_BLOCK_NOTIFICATION or \
                        msg_type == MessageTypes.FAIL_BLOCK_NOTIFICATION:

                    pass

            await services.defer()

    async def handle_sbb_router(self):
        pass

    async def handle_public_router(self):
        pass