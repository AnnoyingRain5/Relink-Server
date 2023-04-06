import asyncio
import websockets
import json
import communication
import hashlib

clients = []
messages = []


async def echo(websocket):
    clients.append(websocket)
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


async def messageHandler(websocket, packet: communication.message):
    messages.append(packet)
    print(packet.json)
    websockets.broadcast(clients, packet.json)  # type: ignore


async def commandHandler(websocket, packet: communication.command):
    pass


async def loginHandler(websocket, packet: communication.loginRequest):
    result = communication.result()
    database = json.load(open("users.json", "r"))
    if packet.username in database:
        if database[packet.username] == hashlib.sha256(packet.password.encode()).hexdigest():
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
        database[packet.username] = hashlib.sha256(
            packet.password.encode()).hexdigest()
        with open("users.json", "w") as f:
            json.dump(database, f)

    else:
        result.result = False
        result.reason = "Username is already in use"
    await websocket.send(result.json)


async def main():
    async with websockets.serve(echo, "0.0.0.0", 8765):  # type: ignore
        await asyncio.Future()  # run forever

asyncio.run(main())
