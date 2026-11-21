import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

APPLICATION_LOG_CHANNEL_ID = int(
    os.environ["APPLICATION_LOG_CHANNEL_ID"]
)

DEVELOPER_ROLE_ID = int(
    os.environ["DEVELOPER_ROLE_ID"]
)

ALPHA_TESTER_ROLE_ID = int(
    os.environ["ALPHA_TESTER_ROLE_ID"]
)

STAFF_ROLE_ID = int(
    os.environ["STAFF_ROLE_ID"]
)

DATABASE_PATH = os.getenv(
    "DATABASE_PATH", "applications.db"
)

EMBED_COLOR = 0x5865F2
SERVER_NAME = "TomoBao Server"
