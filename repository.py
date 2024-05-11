import sqlite3


class Repository:
    def __init__(self):
        self.connection = sqlite3.connect("database/inline_roller.db")
        self.cursor = self.connection.cursor()
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS server_config (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            guild_id VARCHAR(255) NOT NULL UNIQUE,
            config JSON NOT NULL
        )""")
        self.cursor.close()
        self.connection.close()

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
    
    def set_dump_channel(self, guild_id: str, dump_channel_id: str) -> None:
        query = """
        INSERT INTO server_config (guild_id, config)
        VALUES (?, JSON_SET('{}', '$.dump_channel_id', ?))
        ON CONFLICT(guild_id) DO UPDATE
            SET config = JSON_SET(config, '$.dump_channel_id', ?)
        """

        with self as db:
            db.cursor.execute(query, (
                guild_id, dump_channel_id,
                dump_channel_id))
            db.connection.commit()
