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

# init constants
if os.getenv("SERVER_ADDRESS") == None:
    IP_ADDRESS = requests.get("https://api.ipify.org").content.decode("utf-8")
else:
    # the IP address is never used if the env var exists
    IP_ADDRESS = ""


class preferences():
    '''Main preferences class

    This class handles getting environment varables from the system, or falling back to default values
    if they are not present'''

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


class User():
    '''Main user class

    This class is used to store information about the current state of a user;
    what channel they are in, if they are in a federated server, their username, etc'''

    def __init__(self, username: str):
        self.username = username
        self.channel: str = prefs.DEFAULT_CHANNEL
        self.federatedWebsocket: WebSocketClientProtocol | None = None
        self.federatedServerManagerTask: asyncio.Task | None = None

# init constants

 # characters that should be considered invalid for channel names and usernames
INVALID_CHARS = ("!", "#", "$", "%", "^", "&", "'", '"', "*", "(", ")",
                 "<", ">", "/", "\\", "[", "]", "|", " ", ",", "~", "`", "+")
# Extension of the tuple above; these characters are also invalid in usernames
INVALID_USERNAME_CHARS_EXT = (".", ":", "@")

# init variables

prefs = preferences()
users: dict[WebSocketServerProtocol, User] = {}
messages = []


async def server(websocket: WebSocketServerProtocol):
    '''Main function, handles recieving packets and calling the appropriate function depending on packet type'''
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
        # work out what type of packet it is and run the corresponding function
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
            case None:
                print(
                    f"Unknown packet type. JSON data is as follows: {rawpacket}")
            case _:
                print(
                    f"Unknown packet type: {type(packet)}. JSON data is as follows: {rawpacket}")


async def FederatedServerManager(server, packet, userwebsocket: WebSocketServerProtocol):
    '''Function to connect to and get packets from federated servers, then pass them to the client'''
    async with websockets.client.connect(server) as FederatedServer:
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
        # receive messages from federated server loop
        while True:
            rawFederatedPacket = await FederatedServer.recv()
            await userwebsocket.send(rawFederatedPacket)


async def logoffHandler(websocket: WebSocketServerProtocol):
    '''Handles logoff events'''
    await websocket.wait_closed()
    # if we reach this point, the connection has closed
    # we can now remove them from the users list
    # and announce to all users in the same channel
    logoffuser = users[websocket]
    del users[websocket]
    for userWebsocket, user in users.items():
        if user.channel == logoffuser.channel:  # same channel
            message = communication.System()
            message.text = f"{logoffuser.username} just logged off"
            await userWebsocket.send(message.json)


async def SendServerWelcome(websocket: WebSocketServerProtocol):
    '''Function handling sending the welcome message to users'''
    message = communication.System()
    message.text = prefs.WELCOME_MESSAGE
    await websocket.send(message.json)


async def messageHandler(websocket: WebSocketServerProtocol, message: communication.Message):
    '''Handles Message packets'''
    messages.append(message)
    print(users[websocket].channel)
    print(message.json)
    # partially reconstruct packet in case of tampering
    message.username = users[websocket].username
    # if it is a direct message
    if message.isDM:
        for userWebsocket, user in users.items():
            # if they are the correct user
            if f"@{user.username}" == users[websocket].channel:
                await userWebsocket.send(message.json)
                await websocket.send(message.json)
                break
        else:
            # We did not break out of the loop, the user must not be online
            sysmessage = communication.System()
            sysmessage.text = f"Failed to send DM: user {users[websocket].channel} is offline or does not exist."
            await websocket.send(sysmessage.json)
    else:
        # it is not a direct message
        mentions = re.findall("@\\S\\S*", message.text)
        for userWebsocket, user in users.items():
            # if we are in the same channel
            if user.channel == users[websocket].channel:
                await userWebsocket.send(message.json)
            # send a notification if it mentions them
            if f"@{user.username}" in mentions:
                notification = communication.Notification()
                notification.type = "mention"
                # if they are a federated user, append the server address
                if "@" in user.username:
                    notification.location = f"{users[websocket].channel}@{prefs.SERVER_ADDRESS}"
                else:
                    notification.location = users[websocket].channel
                await userWebsocket.send(notification.json)


async def commandHandler(websocket: WebSocketServerProtocol, packet: communication.Command):
    '''Handles command packets, run the corresponding function based on what type of command it is'''
    match packet.name:
        case "switch":
            await switchcommand(websocket, packet)
        case "list":
            await listcommand(websocket, packet)
        case "help":
            await helpcommand(websocket, packet)
        case _:
            # Command is not known to the server
            message = communication.System()
            message.text = "Unknown command."
            await websocket.send(message.json)


async def helpcommand(websocket: WebSocketServerProtocol, packet: communication.Command):
    '''Sends a list of commands to the client'''
    message = communication.System()
    message.text = "Registered commands are as follows:\n"
    message.text += "/switch <channel>\n"
    message.text += "/list\n"
    message.text += "/help"
    await websocket.send(message.json)


async def FederationHandler(websocket: WebSocketServerProtocol, packet: communication.FederationRequest):
    '''Handles other servers attempting to federate to this one'''
    # create a user object
    user = User(packet.username)
    user.channel = packet.channel
    # add them to the users list
    users[websocket] = user
    # schedule the logoff handler
    asyncio.create_task(logoffHandler(websocket))
    # send the welcome message
    await SendServerWelcome(websocket)


async def switchcommand(websocket: WebSocketServerProtocol, packet: communication.Command):
    '''Handles the /switch command by switching the channel the user is in
    and federating to another server if it is requested'''
    # if the channel is federated
    if users[websocket].federatedServerManagerTask is not None:  # if the user is federated
        users[websocket].federatedServerManagerTask.cancel()  # type: ignore

    # if there are any invalid characters in the channel name
    if any(char in packet.args[0] for char in INVALID_CHARS):
        message = communication.System()
        message.text = "The following characters are not allowed in channel names:\n"
        message.text += " ".join(INVALID_CHARS) + "\n"
        message.text += "The channel you tried to switch to includes one of these characters."
        await websocket.send(message.json)
        return  # exit the function here

    # if the user is wanting to connect to a federated server
    if "@" in packet.args[0] and not (packet.args[0].startswith("@") and len(packet.args[0].split("@")) == 2):
        server = packet.args[0].split("@")[-1]
        if ":" in server:  # if a port is specified
            server = f"ws://{server}"
        else:
            # no port specified, use the default port
            server = f"ws://{server}:8765"
        # schedule the federation manager and add it to the user object
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
    '''Handles the /list command by sending a list of online users to the client'''
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
    '''Handles login packets by checking usernames and passwords'''
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
                # if we did not find the user in the list of online users, let them in
                users[websocket] = User(packet.username)
                asyncio.create_task(logoffHandler(websocket))
                result.result = True

        else:
            # if the password is incorrect
            result.result = False
            result.reason = "Incorrect password"
    else:
        # if the user does not have an account on this server
        result.result = False
        result.reason = "Username not found"
    await websocket.send(result.json)

    if result.result:
        # if it was successful, switch the channel and send the server welcome message
        message = communication.ChannelChange()
        message.channel = prefs.DEFAULT_CHANNEL
        await websocket.send(message.json)
        await SendServerWelcome(websocket)


async def signupHandler(websocket: WebSocketServerProtocol, packet: communication.SignupRequest):
    '''Handles requests to sign up to the server'''
    result = communication.Result()
    database = json.load(open("./db/users.json", "r", encoding="utf-8"))
    # if the username contains invalid characters
    if any(char in packet.username for char in INVALID_CHARS + INVALID_USERNAME_CHARS_EXT) or "@" in packet.username:
        result.result = False
        result.reason = "Your username contains invalid characters. The following characters are considered invalid in a username:\n"
        result.reason += " ".join(INVALID_CHARS) + " " + \
            " ".join(INVALID_USERNAME_CHARS_EXT)
        await websocket.send(result.json)
    elif packet.username not in database:  # if the username is not already taken
        result.result = True
        # hash the password
        passwordhash = hashlib.sha256(packet.password.encode()).hexdigest()
        # add the hashed password to the database
        database[packet.username] = passwordhash
        with open("./db/users.json", "w", encoding="utf-8") as f:
            json.dump(database, f)
        # log the user in, set their channel and send a welcome message
        users[websocket] = User(packet.username)
        message = communication.ChannelChange()
        message.channel = prefs.DEFAULT_CHANNEL
        await websocket.send(result.json)
        await websocket.send(message.json)
        await SendServerWelcome(websocket)
    else:
        # tell the user that the  username is in use
        result.result = False
        result.reason = "Username is already in use"
        await websocket.send(result.json)


async def main():
    '''Inital function, starts the server using the Websockets library'''
    async with websockets.server.serve(server, "0.0.0.0", prefs.PORT):
        await asyncio.Future()  # run forever

asyncio.run(main())
