import asyncio
import json
import hashlib
import re
import websockets
from websockets.server import WebSocketServerProtocol as WebsocketProtocol
import communication


CURSOR_UP = '\033[F'
DEFAULT_CHANNEL = "general"


class User():
    def __init__(self, username):
        self.username = username
        self.channel = DEFAULT_CHANNEL


users: dict[WebsocketProtocol, User] = {}
messages = []


async def echo(websocket):
    async for packet in websocket:
        packet = communication.packet(packet)
        match type(packet):
            case communication.Message:
                await messageHandler(websocket, packet)  # type: ignore
            case communication.Command:
                await commandHandler(websocket, packet)  # type: ignore
            case communication.LoginRequest:
                await loginHandler(websocket, packet)  # type: ignore
            case communication.SignupRequest:
                await signupHandler(websocket, packet)  # type: ignore
            case _:
                print(f"oops! we got a {type(packet)}.")


async def logoffHandler(websocket):
    await websocket.wait_closed()
    # if we reach this point, the connection has closed
    # we can now remove them from the users list
    # announce to all users in the channel
    logoffuser = users[websocket]
    del users[websocket]
    for userWebsocket, user in users.items():
        if user.channel == logoffuser.channel:  # same channel
            message = communication.System()
            message.text = f"{logoffuser.username} just logged off"
            await userWebsocket.send(message.json)


async def messageHandler(websocket: WebsocketProtocol, message: communication.Message):
    messages.append(message)
    print(message.json)
    # reconstruct packet in case of tampering
    message.username = users[websocket].username
    if message.isDM:
        for userWebsocket, user in users.items():
            # if they are the correct user
            if f"@{user.username}" == users[websocket].channel:
                await userWebsocket.send(message.json)
                await websocket.send(message.json)
                break
        else:
            sysmessage = communication.System()
            sysmessage.text = f"Failed to send DM: user {users[websocket].channel} is offline or does not exist."
            await websocket.send(sysmessage.json)
    else:
        mentions = re.findall("@\\S\\S*", message.text)
        for userWebsocket, user in users.items():
            # if we are in the same channel
            if user.channel == users[websocket].channel:
                await userWebsocket.send(message.json)
            if f"@{user.username}" in mentions:
                notificiation = communication.Notification()
                notificiation.location = users[websocket].channel
                notificiation.type = "mention"
                await userWebsocket.send(notificiation.json)


async def commandHandler(websocket: WebsocketProtocol, packet: communication.Command):
    match packet.name:
        case "switch":
            await switchcommand(websocket, packet)
        case "list":
            await listcommand(websocket, packet)
        case "help":
            await helpcommand(websocket, packet)
        case _:
            message = communication.System()
            message.text = "Unknown command."
            await websocket.send(message.json)


async def helpcommand(websocket: WebsocketProtocol, packet: communication.Command):
    message = communication.System()
    message.text = "Registered commands are as follows:\n"
    message.text += "/switch <channel>\n"
    message.text += "/list\n"
    message.text += "/help"
    await websocket.send(message.json)


async def switchcommand(websocket: WebsocketProtocol, packet: communication.Command):
    # switch the channel
    users[websocket].channel = packet.args[0]
    # tell the client that the channel has changed
    message = communication.ChannelChange()
    message.channel = packet.args[0]
    await websocket.send(message.json)


async def listcommand(websocket: WebsocketProtocol, packet: communication.Command):
    userlist = "Logged in users are: "
    channeluserlist = "Users currently in your channel are: "
    # get all of the users
    for _, otherUser in users.items():
        # add them to the message
        userlist += f"{otherUser.username}, "
        # if they are in the same channel
        if otherUser.channel == users[websocket].channel:
            channeluserlist += f"{otherUser.username}, "
    # remove the last commas
    userlist = userlist.removesuffix(", ")
    channeluserlist = channeluserlist.removesuffix(", ")
    # prepare and send the message
    message = communication.System()
    message.text = f"{userlist}\n{channeluserlist}"
    await websocket.send(message.json)


async def loginHandler(websocket: WebsocketProtocol, packet: communication.LoginRequest):
    result = communication.Result()
    database = json.load(open("users.json", "r", encoding="utf-8"))
    if packet.username in database:
        if database[packet.username] == hashlib.sha256(packet.password.encode()).hexdigest():
            # correct username and password
            for _, user in users.items():
                if user.username == packet.username:
                    # if they are already logged in from another location
                    result.result = False
                    result.reason = "You are already logged in from another location."
                    break
            else:
                users[websocket] = User(packet.username)
                asyncio.create_task(logoffHandler(websocket))
                result.result = True

        else:
            result.result = False
            result.reason = "Incorrect password"
    else:
        result.result = False
        result.reason = "Username not found"
    await websocket.send(result.json)
    if result.result:
        message = communication.ChannelChange()
        message.channel = DEFAULT_CHANNEL
        await websocket.send(message.json)


async def signupHandler(websocket: WebsocketProtocol, packet: communication.SignupRequest):
    result = communication.Result()
    database = json.load(open("users.json", "r", encoding="utf-8"))
    if packet.username not in database:
        result.result = True
        passwordhash = hashlib.sha256(packet.password.encode()).hexdigest()
        database[packet.username] = passwordhash
        with open("users.json", "w", encoding="utf-8") as f:
            json.dump(database, f)
        users[websocket] = User(packet.username)
        message = communication.ChannelChange()
        message.channel = DEFAULT_CHANNEL
        await websocket.send(message.json)
    else:
        result.result = False
        result.reason = "Username is already in use"
    await websocket.send(result.json)


async def main():
    async with websockets.serve(echo, "0.0.0.0", 8765):  # type: ignore
        await asyncio.Future()  # run forever

asyncio.run(main())
