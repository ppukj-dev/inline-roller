import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv('.env')
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASS = os.getenv('MYSQL_PASS')
MYSQL_DB = os.getenv('MYSQL_DB')


def get_config(guild_id: str):

    mydb = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASS,
            database=MYSQL_DB
    )

    query = """
    SELECT 
        config 
    FROM server_config
    WHERE guild_id = %s
    LIMIT 1
    """

    cursor = mydb.cursor(buffered=True)
    cursor.execute(query, (guild_id,))
    result = cursor.fetchone()
    cursor.close()
    mydb.close()

    return result


def set_dump_channel(guild_id: str, dump_channel_id: str) -> None:

    mydb = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASS,
            database=MYSQL_DB
    )

    query = """
    INSERT INTO server_config (guild_id, config)
    VALUES (%s, JSON_SET('\{\}', '$.dump_channel_id', %s))
    ON DUPLICATE KEY UPDATE
        config = JSON_SET(config, '$.dump_channel_id', %s)
    """

    cursor = mydb.cursor(buffered=True)
    cursor.execute(query, (guild_id, dump_channel_id, dump_channel_id))
    mydb.commit()
    cursor.close()
    mydb.close()
