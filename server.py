import asyncio
import json
import hashlib
import re
import os
from typing import Any
import websockets.server
import websockets.client
from websockets.server import WebSocketServerProtocol
from websockets.client import WebSocketClientProtocol
import Relink_Communication.communication as communication
import requests

try:  # use dotenv for values if possible
    import dotenv
    dotenv.load_dotenv()
except:  # it's okay if dotenv is not present
    pass

if os.getenv("SERVER_ADDRESS") == None:
    IP_ADDRESS = requests.get("https://api.ipify.org").content.decode("utf-8")
else:
    # the IP address is never used if the env var exists
    IP_ADDRESS = ""

INVALID_CHARS = ("!", "#", "$", "%", "^", "&", "'", '"', "*", "(", ")",
                 "<", ">", "/", "\\", "[", "]", "|", " ", ",", "~", "`", "+")
INVALID_USERNAME_CHARS_EXT = (".", ":", "@")


class preferences():
    def __init__(self):
        self.PORT: int
        self.DEFAULT_CHANNEL: str
        self.SERVER_ADDRESS: str
        self.WELCOME_MESSAGE: str

    def __getattribute__(self, __name: str) -> str:
        defaults = {
            "PORT": 8765,
            "DEFAULT_CHANNEL": "general",
            "SERVER_ADDRESS": IP_ADDRESS,
            "WELCOME_MESSAGE": "Welcome to the test server!"
        }
        envvar = os.getenv(f"RLS_{__name}")
        if envvar is not None:
            return envvar
        else:
            try:
                return defaults[__name]
            except:
                raise KeyError

    def __setattr__(self, __name: str, __value: Any) -> None:
        raise NotImplementedError


prefs = preferences()


class User():
    def __init__(self, username: str):
        self.username = username
        self.channel: str = prefs.DEFAULT_CHANNEL
        self.federatedWebsocket: WebSocketClientProtocol | None = None
        self.federatedServerManagerTask: asyncio.Task | None = None


users: dict[WebSocketServerProtocol, User] = {}
messages = []


async def SendServerWelcome(websocket: WebSocketServerProtocol):
    message = communication.System()
    message.text = prefs.WELCOME_MESSAGE
    await websocket.send(message.json)


async def server(websocket: WebSocketServerProtocol):
    async for rawpacket in websocket:
        packet = communication.packet(rawpacket)
        # if they are logged in
        if websocket in users:
            # if they are in a federated server
            if users[websocket].federatedWebsocket is not None:
                # if it is not a command
                if type(packet) != communication.Command:
                    await users[websocket].federatedWebsocket.send(  # type: ignore
                        rawpacket)
                    continue
                else:  # it must be a command
                    cmdname = communication.packet(
                        rawpacket).name.lower()  # type: ignore
                    if cmdname == "switch":
                        await commandHandler(websocket, packet)
                    else:
                        await users[websocket].federatedWebsocket.send(  # type: ignore
                            rawpacket)
                        continue
        match type(packet):
            case communication.Message:
                await messageHandler(websocket, packet)  # type: ignore
            case communication.Command:
                await commandHandler(websocket, packet)  # type: ignore
            case communication.LoginRequest:
                await loginHandler(websocket, packet)  # type: ignore
            case communication.SignupRequest:
                await signupHandler(websocket, packet)  # type: ignore
            case communication.FederationRequest:
                await FederationHandler(websocket, packet)  # type: ignore
            case _:
                print(f"oops! we got a {type(packet)}.")


async def FederatedServerManager(server, packet, userwebsocket: WebSocketServerProtocol):
    async with websockets.client.connect(server) as FederatedServer:
        print("connected")
        print(packet.args[0].split("@"))

        # switch the channel
        users[userwebsocket].channel = packet.args[0]
        # tell the client that the channel has changed
        message = communication.ChannelChange()
        message.channel = packet.args[0]
        await userwebsocket.send(message.json)
        request = communication.FederationRequest()
        request.channel = packet.args[0].split("@")[0]
        request.username = f"{users[userwebsocket].username}@{prefs.SERVER_ADDRESS}"
        await FederatedServer.send(request.json)
        users[userwebsocket].federatedWebsocket = FederatedServer
        # recieve messages from federated server loop
        while True:
            rawFederatedPacket = await FederatedServer.recv()
            print("got a federated packet!")
            print(rawFederatedPacket)
            await userwebsocket.send(rawFederatedPacket)


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


async def messageHandler(websocket: WebSocketServerProtocol, message: communication.Message):
    messages.append(message)
    print(users[websocket].channel)
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
            # send a notification if it mentions them
            if f"@{user.username}" in mentions:
                notificiation = communication.Notification()
                notificiation.type = "mention"
                # if they are a federated user, append the server address
                if "@" in user.username:
                    notificiation.location = f"{users[websocket].channel}@{prefs.SERVER_ADDRESS}"
                else:
                    notificiation.location = users[websocket].channel
                await userWebsocket.send(notificiation.json)


async def commandHandler(websocket: WebSocketServerProtocol, packet: communication.Command):
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


async def helpcommand(websocket: WebSocketServerProtocol, packet: communication.Command):
    message = communication.System()
    message.text = "Registered commands are as follows:\n"
    message.text += "/switch <channel>\n"
    message.text += "/list\n"
    message.text += "/help"
    await websocket.send(message.json)


async def FederationHandler(websocket: WebSocketServerProtocol, packet: communication.FederationRequest):
    user = User(packet.username)
    user.channel = packet.channel
    users[websocket] = user
    asyncio.create_task(logoffHandler(websocket))
    await SendServerWelcome(websocket)


async def switchcommand(websocket: WebSocketServerProtocol, packet: communication.Command):
    # if the channel is federated
    if users[websocket].federatedServerManagerTask is not None:
        users[websocket].federatedServerManagerTask.cancel()  # type: ignore

    if any(char in packet.args[0] for char in INVALID_CHARS):
        message = communication.System()
        message.text = "The following characters are not allowed in channel names:\n"
        message.text += " ".join(INVALID_CHARS) + "\n"
        message.text += "The channel you tried to switch to includes one of these characters."
        await websocket.send(message.json)
        return

    if "@" in packet.args[0] and not (packet.args[0].startswith("@") and len(packet.args[0].split("@")) == 2):
        print("switching to federated")
        server = packet.args[0].split("@")[-1]
        if ":" in server:
            server = f"ws://{server}"
        else:
            server = f"ws://{server}:8765"
        print(f"ready to connect to {server}")
        users[websocket].federatedServerManagerTask = asyncio.create_task(
            FederatedServerManager(server, packet, websocket))
    else:
        users[websocket].federatedWebsocket = None
    # switch the channel
    users[websocket].channel = packet.args[0]
    # tell the client that the channel has changed
    message = communication.ChannelChange()
    message.channel = packet.args[0]
    await websocket.send(message.json)


async def listcommand(websocket: WebSocketServerProtocol, packet: communication.Command):
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


async def loginHandler(websocket: WebSocketServerProtocol, packet: communication.LoginRequest):
    result = communication.Result()
    database = json.load(open("./db/users.json", "r", encoding="utf-8"))
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
        message.channel = prefs.DEFAULT_CHANNEL
        await websocket.send(message.json)
        await SendServerWelcome(websocket)


async def signupHandler(websocket: WebSocketServerProtocol, packet: communication.SignupRequest):
    result = communication.Result()
    database = json.load(open("./db/users.json", "r", encoding="utf-8"))
    if any(char in packet.username for char in INVALID_CHARS + INVALID_USERNAME_CHARS_EXT) or "@" in packet.username:
        result.result = False
        result.reason = "Your username contains invalid characters. The following characters are considered invalid in a username:\n"
        result.reason += " ".join(INVALID_CHARS) + " " + \
            " ".join(INVALID_USERNAME_CHARS_EXT)
        await websocket.send(result.json)
    elif packet.username not in database:
        result.result = True
        passwordhash = hashlib.sha256(packet.password.encode()).hexdigest()
        database[packet.username] = passwordhash
        with open("./db/users.json", "w", encoding="utf-8") as f:
            json.dump(database, f)
        users[websocket] = User(packet.username)
        message = communication.ChannelChange()
        message.channel = prefs.DEFAULT_CHANNEL
        await websocket.send(result.json)
        await websocket.send(message.json)
        await SendServerWelcome(websocket)
    else:
        result.result = False
        result.reason = "Username is already in use"
        await websocket.send(result.json)


async def main():
    async with websockets.server.serve(server, "0.0.0.0", prefs.PORT):
        await asyncio.Future()  # run forever

asyncio.run(main())
