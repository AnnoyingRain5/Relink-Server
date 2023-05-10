import asyncio
import websockets
import json
import communication
import hashlib
import re
import websockets.server


CURSOR_UP = '\033[F'
DEFAULT_CHANNEL = "general"


class user():
    def __init__(self, username):
        self.username = username
        self.channel = DEFAULT_CHANNEL


users: dict[websockets.server.WebSocketServerProtocol,  # type: ignore
            user] = {}
messages = []


async def echo(websocket):
    async for packet in websocket:
        packet = communication.packet(packet)
        match type(packet):
            case communication.message:
                await messageHandler(websocket, packet)  # type: ignore
            case communication.command:
                await commandHandler(websocket, packet)  # type: ignore
            case communication.loginRequest:
                await loginHandler(websocket, packet)  # type: ignore
            case communication.signupRequest:
                await signupHandler(websocket, packet)  # type: ignore
            case _:
                print(f" oops! we got a {type(packet)}.")


async def logoffHandler(websocket):
    await websocket.wait_closed()
    # if we reach this point, the connection has closed
    # we can now remove them from the users list
    # announce to all users in the channel
    logoffuser = users[websocket]
    del users[websocket]
    for userwebsocket in users:
        if users[userwebsocket].channel == logoffuser.channel:  # same channel
            message = communication.system()
            message.text = f"{logoffuser.username} just logged off"
            await userwebsocket.send(message.json)


async def messageHandler(websocket, message: communication.message):
    messages.append(message)
    print(message.json)
    # reconstruct packet in case of tampering
    message.username = users[websocket].username
    if message.isDM:
        for user in users:
            # if they are the correct user
            if f"@{users[user].username}" == users[websocket].channel:
                await user.send(message.json)
                await websocket.send(message.json)
                break
        else:
            sysmessage = communication.system()
            sysmessage.text = f"Failed to send DM: user {users[websocket].channel} is offline or does not exist."
            await websocket.send(sysmessage.json)

    else:
        mentions = re.findall("@\\S\\S*", message.text)
        for user in users:
            # if we are in the same channel
            if users[user].channel == users[websocket].channel:
                await user.send(message.json)
            if f"@{users[user].username}" in mentions:
                notificiation = communication.notification()
                notificiation.location = users[websocket].channel
                notificiation.type = "mention"
                await user.send(notificiation.json)


async def commandHandler(websocket, packet: communication.command):
    match packet.name:
        case "switch":
            await switchcommand(websocket, packet)
        case "list":
            await listcommand(websocket, packet)
        case "help":
            await helpcommand(websocket, packet)
        case _:
            message = communication.system()
            message.text = "Unknown command."
            await websocket.send(message.json)


async def helpcommand(websocket, packet: communication.command):
    message = communication.system()
    message.text = "Registered commands are as follows:\n"
    message.text += "/switch <channel>\n"
    message.text += "/list\n"
    message.text += "/help"
    await websocket.send(message.json)


async def switchcommand(websocket, packet: communication.command):
    # switch the channel
    users[websocket].channel = packet.args[0]
    # tell the client that the channel has changed
    message = communication.channelChange()
    message.channel = packet.args[0]
    await websocket.send(message.json)


async def listcommand(websocket, packet: communication.command):
    userlist = "Logged in users are: "
    channeluserlist = "Users currently in your channel are: "
    # get all of the users
    for userwebsocket in users:
        # add them to the message
        userlist += f"{users[userwebsocket].username}, "
        # if they are in the same channel
        if users[userwebsocket].channel == users[websocket].channel:
            channeluserlist += f"{users[userwebsocket].username}, "
    # remove the last commas
    userlist = userlist.removesuffix(", ")
    channeluserlist = channeluserlist.removesuffix(", ")
    # prepare and send the message
    message = communication.system()
    message.text = f"{userlist}\n{channeluserlist}"
    await websocket.send(message.json)


async def loginHandler(websocket, packet: communication.loginRequest):
    result = communication.result()
    database = json.load(open("users.json", "r"))
    if packet.username in database:
        if database[packet.username] == hashlib.sha256(packet.password.encode()).hexdigest():
            # correct username and password
            for userwebsocket in users:
                if users[userwebsocket].username == packet.username:
                    # if they are already logged in from another location
                    result.result = False
                    result.reason = "You are already logged in from another location."
                    break
            else:
                users[websocket] = user(packet.username)
                asyncio.create_task(logoffHandler(websocket))
                result.result = True

        else:
            result.result = False
            result.reason = "Incorrect password"
    else:
        result.result = False
        result.reason = "Username not found"
    await websocket.send(result.json)
    if result.result == True:
        message = communication.channelChange()
        message.channel = DEFAULT_CHANNEL
        await websocket.send(message.json)


async def signupHandler(websocket, packet: communication.signupRequest):
    result = communication.result()
    database = json.load(open("users.json", "r"))
    if packet.username not in database:
        result.result = True
        passwordhash = hashlib.sha256(packet.password.encode()).hexdigest()
        database[packet.username] = passwordhash
        with open("users.json", "w") as f:
            json.dump(database, f)
        users[websocket] = user(packet.username)
    else:
        result.result = False
        result.reason = "Username is already in use"
    await websocket.send(result.json)


async def main():
    async with websockets.serve(echo, "0.0.0.0", 8765):  # type: ignore
        await asyncio.Future()  # run forever

asyncio.run(main())
