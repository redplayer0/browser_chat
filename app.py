from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from litestar import (
    Litestar,
    MediaType,
    Request,
    WebSocket,
    get,
    post,
    websocket_listener,
)
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import WebSocketDisconnect
from litestar.response import Template
from litestar.static_files.config import StaticFilesConfig
from litestar.template.config import TemplateConfig


@dataclass
class Game:
    players: list[Player] = field(default_factory=list)

    def add_player(self, player: Player):
        if len(self.players) < 2:
            self.players.append(player)


def div_message(message):
    return f"<div id=history hx-swap-oob=afterbegin><div class='message'>{message}</div></div>"


def div_message_input(room_id):
    return f"""
        <div hx-ext="ws" ws-connect="/room/{room_id}">
          <form id="form" ws-send _="on submit me.reset()">
            <input name="message">
            <div class="room_name">{room_id}</div>
          </form>
        </div>
    """


HISTORY = 10
users = []
rooms = {}


@asynccontextmanager
# async def lifespan(
#     socket: WebSocket, channels: ChannelsPlugin, room_id: str
# ) -> AsyncContextManager[None]:
async def lifespan(socket: WebSocket, channels: ChannelsPlugin, room_id: str):
    # here create the user
    users.append(socket.client)
    rooms[room_id].append(socket.client)
    async with channels.start_subscription(room_id, history=HISTORY) as subscriber:
        try:
            async with subscriber.run_in_background(socket.send_data):
                yield
        except WebSocketDisconnect:
            # here remove the user
            rooms[room_id].remove(socket.client)
            return


@websocket_listener("/room/{room_id:str}", connection_lifespan=lifespan)
async def chatroom(
    data: dict[str, str], socket: WebSocket, channels: ChannelsPlugin, room_id: str
) -> None:
    # print(socket.client)
    # print(channels._backend.get_history(room_id, 50))
    if msg := data["message"]:
        channels.publish(div_message(msg), channels=[room_id])


@get("/", media_type=MediaType.HTML)
async def index() -> str:
    return Template(template_name="index.html", context={})


@post(path="/join")
async def join(data: dict[str, str], request: Request) -> str:
    room_id = data["room_id"]
    if not room_id:
        return
    if room_id in rooms:
        if len(rooms[room_id]) < 2:
            return div_message_input(room_id)
        else:
            return "<div id='chatroom' hx-swap-oob=afterbegin><div class='info' _='init wait 2s then remove me'>Room Full</div></div>"
    else:
        rooms[room_id] = []
        return div_message_input(room_id)


channels_plugin = ChannelsPlugin(
    backend=MemoryChannelsBackend(history=HISTORY),
    arbitrary_channels_allowed=True,
    # create_ws_route_handlers=True,
)


template_config = TemplateConfig(
    directory=Path("templates"),
    engine=JinjaTemplateEngine,
)

app = Litestar(
    route_handlers=[index, join, chatroom],
    plugins=[channels_plugin],
    template_config=template_config,
    static_files_config=[
        StaticFilesConfig(directories=["assets"], path="/", name="assets")
    ],
)
