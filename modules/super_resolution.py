# python
import asyncio
import re
from typing import Optional

import aiohttp
from config import SUPER_RESOLUTION_SERVICE_URL

# ariadne
from graia.ariadne.app import Ariadne
from graia.ariadne.event.message import GroupMessage
from graia.ariadne.message.chain import MessageChain
from graia.ariadne.message.element import Image, Quote
from graia.ariadne.model import Group, Member

# saya
from graia.saya import Saya, Channel
from graia.saya.builtins.broadcast.schema import ListenerSchema

sr_cmd_pattern = re.compile(r'(@\d+ )?2x')


# 插件信息
__name__ = "super-resolution"
__description__ = "call my web app http://sr-orenji.ml:6990/ to generate a 2x version of the designated image"
__author__ = "Orenji"
__usage__ = "reply to an image, and type \"2x\" to call this api"

saya = Saya.current()
channel = Channel.current()

channel.name(__name__)
channel.description(f"{__description__}\n使用方法：{__usage__}")
channel.author(__author__)

async def run_super_resolution(image_bytes: bytes) -> Optional[str]:
    async with aiohttp.ClientSession() as session:
        # send sr request with data={image:binary, tile_mode:str}
        async with session.post(SUPER_RESOLUTION_SERVICE_URL, data={"raw_image": image_bytes, "tile_mode":"4"}) as response:
            data = await response.json()
            if "task_id" not in data:
                print("requesting super resolution service failed!")
                return
            task_id = data["task_id"]

        # try to retrieve result every one second
        for i in range(600):
            await asyncio.sleep(1)
            async with session.get(SUPER_RESOLUTION_SERVICE_URL+'get-result/{}'.format(task_id)) as response:
                print(response)
                data = await response.json()
                if "state" not in data:
                    print("requesting sr result failed!")
                    return
                if data["state"] == True:
                    return data["image"] # sr-inference success, return image in base64

@channel.use(ListenerSchema(listening_events=[GroupMessage]))
async def group_message_listener(
    app: Ariadne,
    message: MessageChain,
    sender: Member,
    group: Group
):

    text = message.asDisplay()
    if re.match(sr_cmd_pattern, text) != None: # has pattern like "@12768888 2x", maybe a sr command

        # fetch the reply object
        if Quote not in message: return
        quote = message.get(Quote)[0]

        # fetch the original message that the reply refers to. The given api quote.origin can fetch the original messageChain, but the Image inside is transcoded to Plain text (we can't get the original image this way).
        original_event = await Ariadne.getMessageFromId(self=app, messageId=quote.id)
        if not original_event: return
        original_message = original_event.messageChain
        if Image not in original_message: return
        image = original_message.get(Image)[0]

        # try to request super resolution service using this image. If success, return the upscaled image
        try:
            image_bytes = await image.get_bytes()
            sr_image_base64 = await run_super_resolution(image_bytes = image_bytes)
            await app.sendGroupMessage(group, MessageChain([Image(base64 = sr_image_base64)]))

        except Exception as e: # if the image is broken(no url and no base64), return
            print(e)
