import asyncio
import websockets
import json
import communication
import hashlib

CURSOR_UP = '\033[F'

users = {}
messages = []

DEFAULT_CHANNEL = "general"


class user():
    def __init__(self, username):
        self.username = username
        self.channel = DEFAULT_CHANNEL


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
    print(f"{users[websocket].username} just logged off!")
    # if we reach this point, the connection has closed
    # we can now remove them from the users list
    del users[websocket]


async def messageHandler(websocket, packet: communication.message):
    messages.append(packet)
    print(packet.json)
    # reconstruct packet in case of tampering
    message = communication.message()
    message.username = users[websocket].username
    message.text = packet.text

    for user in users:
        # if we are in the same channel
        if users[user].channel == users[websocket].channel:
            await user.send(message.json)


async def commandHandler(websocket, packet: communication.command):
    match packet.name:
        case "switch":
            await switchcommand(websocket, packet)
        case "list":
            await listcommand(websocket, packet)


async def switchcommand(websocket, packet: communication.command):
    users[websocket].channel = packet.args[0]
    message = communication.system()
    message.text = f"You have switched to {packet.args[0]}"
    message.response = True
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
    message.response = True
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
