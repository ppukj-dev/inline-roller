import json
import sqlite3


class Repository:
    def __init__(self):
        pass

    def __enter__(self):
        self.connection = sqlite3.connect("database/inline_roller.db")
        self.cursor = self.connection.cursor()
        return self

    def __exit__(self, type, value, traceback):
        self.cursor.close()
        self.connection.close()


class ConfigRepository(Repository):
    def __init__(self):
        super().__init__()
        self.connection = sqlite3.connect("database/inline_roller.db")
        self.cursor = self.connection.cursor()
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS server_config (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            guild_id VARCHAR(255) NOT NULL UNIQUE,
            config JSON NOT NULL
        )""")
        self.cursor.close()
        self.connection.close()

    def get_config(self, guild_id: str):
        query = """
        SELECT
            config
        FROM server_config
        WHERE guild_id = ?
        LIMIT 1
        """

        with self as db:
            db.cursor.execute(query, (guild_id,))
            result = db.cursor.fetchone()

        return result

    def set_config(self, guild_id: str, dump_channel_id: int,
                   thread_dump_target: str) -> None:
        """Upsert the full server config for ``guild_id``.

        The whole config object is (re)written, so callers pass every field
        they want persisted rather than patching individual keys.
        """
        config = json.dumps({
            "dump_channel_id": dump_channel_id,
            "thread_dump_target": thread_dump_target,
        })
        query = """
        INSERT INTO server_config (guild_id, config)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE
            SET config = ?
        """

        with self as db:
            db.cursor.execute(query, (guild_id, config, config))
            db.connection.commit()


class RollHistoryRepository(Repository):
    def __init__(self):
        super().__init__()
        self.connection = sqlite3.connect("database/inline_roller.db")
        self.cursor = self.connection.cursor()
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS history_dice (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            character_name VARCHAR(255) NOT NULL,
            dice_roll VARCHAR(255) NOT NULL,
            result VARCHAR(255) NOT NULL,
            expression TEXT NOT NULL,
            crit INTEGER NOT NULL,
            guild_id VARCHAR(255) NOT NULL,
            room_name VARCHAR(255) NOT NULL
        )""")
        self.cursor.close()
        self.connection.close()

    def get_history(self, guild_id: str):
        query = """
        SELECT
            character_name, dice_roll, result, expression, crit,
            guild_id, room_name
        FROM history_dice
        WHERE guild_id = ?
        """

        with self as db:
            db.cursor.execute(query, (guild_id,))
            result = db.cursor.fetchall()

        return result

    def add_history(
            self,
            guild_id: str,
            character_name: str,
            dice_roll: str,
            result: str,
            expression: str,
            crit: int,
            room_name: str,
            ) -> None:
        query = """
        INSERT INTO history_dice (
            character_name, dice_roll, result, expression, crit,
            guild_id, room_name
        )
        VALUES (
            ?, ?, ?, ?, ?,
            ?, ?
        )
        """

        with self as db:
            db.cursor.execute(query, (
                character_name, dice_roll, result, expression, crit,
                guild_id, room_name
            ))
            db.connection.commit()
