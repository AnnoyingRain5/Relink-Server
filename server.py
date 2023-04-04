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
                await messageHandler(websocket, packet)
            case communication.command:
                await commandHandler(websocket, packet)
            case communication.loginRequest:
                await loginHandler(websocket, packet)
            case communication.signupRequest:
                await signupHandler(websocket, packet)
            case _:
                print(type(packet))


async def messageHandler(websocket, packet: communication.message):
    messages.append(packet)
    print(packet.json)
    websockets.broadcast(clients, packet.json)


async def commandHandler(websocket, packet: communication.command):
    pass


async def loginHandler(websocket, packet: communication.loginRequest):
    result = communication.result()
    database = json.load(open("users.json", "r"))
    if packet.username in database:
        print(hashlib.sha256(packet.password.encode()).hexdigest())
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
        print(hashlib.sha256(packet.password.encode()).hexdigest())
        database[packet.username] = hashlib.sha256(
            packet.password.encode()).hexdigest()
        json.dump(database, open("users.json", "w"))

    else:
        result.result = False
        result.reason = "Username already in database"
    await websocket.send(result.json)


async def main():
    async with websockets.serve(echo, "0.0.0.0", 8765):
        await asyncio.Future()  # run forever

asyncio.run(main())
