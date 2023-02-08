import asyncio
import websockets

clients = []
async def echo(websocket):
    clients.append(websocket)
    async for message in websocket:

        websockets.broadcast(clients, message)
        print(message)

async def main():
    async with websockets.serve(echo, "localhost", 8765):
        await asyncio.Future()  # run forever

asyncio.run(main())
