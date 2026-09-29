"""Konfigurasi statis skua-lite."""

# --- Endpoint AQW (terverifikasi dari kode client AQW & Skua) ---
GAME_BASE = "https://game.aq.com/game/"
LOGIN_URL = GAME_BASE + "api/login/now"
GAME_VERSION_URL = GAME_BASE + "api/data/gameversion"
SERVER_LIST_URL = "http://content.aq.com/game/api/data/servers"

# --- SmartFox transport ---
EOM = 0x00                    # null byte: akhir setiap paket
SFS_VERSION = "157"           # versi protokol SmartFox di AQW (maj 1, min 5, sub 7 -> "157")
LOGIN_ZONE = "zone_master"    # zone login (Game.cLoginZone)
CLIENT_TOKEN = "SPIDER#0001"  # clientToken (Game.clientToken)

# --- Default target (sesuai permintaan user) ---
DEFAULT_SERVER = "Yorumi"
DEFAULT_MAP = "yulgar-14045"
# Mode farming memakai map sendiri supaya flow-nya tidak bercampur dengan
# sesi asisten yang AFK di Yulgar. Suffix -100000 = private room (Skua).
# Profil combat awal (Mage) menargetkan Water Draconian di Lair.
FARMING_MAP = "lair-100000"
DEFAULT_CELL = "Enter"
DEFAULT_PAD = "Spawn"
DEFAULT_X = 850
DEFAULT_Y = 302
DEFAULT_MOVE_SPEED = 10

# --- Jaringan ---
CONNECT_TIMEOUT = 20.0
RECV_TIMEOUT = 30.0
KEEPALIVE_INTERVAL = 25.0     # detik antara ping SFS

# --- Path storage kredensial ---
STORAGE_DIRNAME = "skua-lite"
CRED_FILENAME = "credentials.enc"
MACHINE_ENTROPY_FILENAME = "machine.key"
