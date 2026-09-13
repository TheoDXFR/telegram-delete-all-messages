"""Delete ALL your messages in every chat: private chats, bots, groups,
supergroups and channels. Extended variant of cleaner.py.

Flow: login -> scan -> summary -> delete -> optionally leave non-owned groups.

Credentials come from env vars API_ID / API_HASH, or from
~/.config/telegram-wipe/api.env (KEY=VALUE lines), or are asked interactively.

Usage:
  python wipe.py                 # scan, show summary, ask confirmation
  python wipe.py --yes           # skip the confirmation gate
  python wipe.py --include-saved # also wipe Saved Messages (default: skipped)
"""

import argparse
import asyncio
import os
import sys

from pyrogram import Client, enums, raw, utils
from pyrogram.errors import FloodWait, UnknownError

from qr_auth import login_with_qr

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.expanduser('~/.config/telegram-wipe/api.env')

SEARCH_CHUNK = 100
HISTORY_CHUNK = 200
DELETE_CHUNK = 100
INTER_CHUNK_SLEEP = 1.0


def load_credentials():
    api_id = os.getenv('API_ID')
    api_hash = os.getenv('API_HASH')
    if not (api_id and api_hash) and os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if '=' not in line:
                    continue
                k, v = line.split('=', 1)
                if k == 'API_ID' and not api_id:
                    api_id = v
                elif k == 'API_HASH' and not api_hash:
                    api_hash = v
    if not (api_id and api_hash):
        api_id = input('Enter your Telegram API id: ')
        api_hash = input('Enter your Telegram API hash: ')
    return int(api_id), api_hash


API_ID, API_HASH = load_credentials()
app = Client(os.path.join(HERE, 'wipe_session'), api_id=API_ID, api_hash=API_HASH)


async def flood_guard(action):
    """Run action(), retrying while Telegram asks us to slow down."""
    while True:
        try:
            return await action()
        except FloodWait as e:
            print(f'  FloodWait: sleeping {e.value}s...')
            await asyncio.sleep(e.value + 1)


async def search_own_ids(chat_id):
    """Message ids authored by us, via server-side search (groups + private chats)."""
    ids = []
    offset = 0
    while True:
        batch = await flood_guard(lambda: collect_search(chat_id, offset))
        ids.extend(batch)
        if len(batch) < SEARCH_CHUNK:
            return ids
        offset += SEARCH_CHUNK


async def collect_search(chat_id, offset):
    batch = []
    async for msg in app.search_messages(chat_id=chat_id, offset=offset,
                                         from_user='me', limit=SEARCH_CHUNK):
        batch.append(msg.id)
    return batch


async def collect_history(chat_id, offset_id):
    batch = []
    async for msg in app.get_chat_history(chat_id, offset_id=offset_id,
                                          limit=HISTORY_CHUNK):
        batch.append(msg)
    return batch


async def history_own_ids(chat_id, me_id):
    """Message ids authored by us, by walking history (channels: search unsupported)."""
    ids = []
    offset_id = 0
    while True:
        messages = await flood_guard(lambda: collect_history(chat_id, offset_id))
        if not messages:
            return ids
        batch = []
        for msg in messages:
            offset_id = msg.id
            if msg.service:
                continue
            if msg.outgoing or (msg.from_user and msg.from_user.id == me_id):
                batch.append(msg.id)
        ids.extend(batch)


async def get_all_chats():
    chats_by_id = {}
    for chat_list in (0, 1):
        async for dialog in app.get_dialogs(chat_list=chat_list):
            if dialog.chat:
                chats_by_id[dialog.chat.id] = dialog.chat
    return list(chats_by_id.values())


def format_chat(chat):
    title = chat.title or chat.first_name or 'Unknown'
    if chat.username:
        title = f'{title} (@{chat.username})'
    kind = {
        enums.ChatType.PRIVATE: 'private',
        enums.ChatType.BOT: 'bot',
        enums.ChatType.GROUP: 'group',
        enums.ChatType.SUPERGROUP: 'supergroup',
        enums.ChatType.CHANNEL: 'channel',
    }.get(chat.type, str(chat.type))
    return f'{title} [{kind}]'


async def scan_chat(chat, me_id):
    """Return list of our message ids in this chat, or raise."""
    if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        return await search_own_ids(chat.id)
    if chat.type == enums.ChatType.CHANNEL:
        # Owned channels are deleted and other channels are left in the final
        # phase. Scanning every public post here is both redundant and prone to
        # Telegram history flood limits.
        return []
    if chat.type in (enums.ChatType.PRIVATE, enums.ChatType.BOT):
        return await search_own_ids(chat.id)
    return []


async def delete_ids(chat, message_ids):
    deleted = 0
    for i in range(0, len(message_ids), DELETE_CHUNK):
        chunk = message_ids[i:i + DELETE_CHUNK]
        while True:
            try:
                await app.delete_messages(chat_id=chat.id, message_ids=chunk,
                                          revoke=True)
            except FloodWait as e:
                print(f'  FloodWait: sleeping {e.value}s...')
                await asyncio.sleep(e.value)
            else:
                break
        deleted += len(chunk)
        print(f'  {format_chat(chat)}: deleted {deleted}/{len(message_ids)}')
        if deleted < len(message_ids):
            await asyncio.sleep(INTER_CHUNK_SLEEP)
    return deleted


async def remove_chat(chat):
    if chat.type in (enums.ChatType.PRIVATE, enums.ChatType.BOT):
        try:
            peer = await app.resolve_peer(chat.id)
            await flood_guard(lambda: app.invoke(raw.functions.messages.DeleteHistory(
                peer=peer, max_id=0, just_clear=False, revoke=True)))
            return 'history_deleted'
        except Exception as e:
            return f'error:{type(e).__name__}'
    if chat.type == enums.ChatType.GROUP:
        try:
            await flood_guard(lambda: app.invoke(raw.functions.messages.DeleteChat(
                chat_id=utils.get_raw_peer_id(chat.id))))
            return 'deleted_owner'
        except Exception:
            try:
                await flood_guard(lambda: app.leave_chat(chat.id))
                peer = await app.resolve_peer(chat.id)
                await flood_guard(lambda: app.invoke(raw.functions.messages.DeleteHistory(
                    peer=peer, max_id=0, just_clear=False, revoke=False)))
                return 'left'
            except Exception as e:
                return f'error:{type(e).__name__}'
    if chat.type not in (enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL):
        return 'not_applicable'
    try:
        member = await flood_guard(lambda: app.get_chat_member(chat.id, 'me'))
        if member.status == enums.ChatMemberStatus.OWNER:
            peer = await app.resolve_peer(chat.id)
            channel = raw.types.InputChannel(
                channel_id=peer.channel_id, access_hash=peer.access_hash)
            await flood_guard(lambda: app.invoke(
                raw.functions.channels.DeleteChannel(channel=channel)))
            return 'deleted_owner'
        await flood_guard(lambda: app.leave_chat(chat.id))
        try:
            peer = await app.resolve_peer(chat.id)
            await flood_guard(lambda: app.invoke(raw.functions.messages.DeleteHistory(
                peer=peer, max_id=0, just_clear=False, revoke=False)))
        except Exception:
            pass
        return 'left'
    except Exception as e:
        return f'error:{type(e).__name__}'


def select_login_method():
    print('\nHow do you want to log in?')
    print('  1. Phone number and confirmation code')
    print('  2. QR code')
    while True:
        choice = input('Insert option number [1]: ').strip() or '1'
        if choice in ('1', '2'):
            return choice
        print('Invalid option selected. Try again.')


async def ensure_logged_in(force_qr=False):
    is_authorized = await app.connect()
    if not is_authorized:
        if force_qr or select_login_method() == '2':
            await app.initialize()
            await login_with_qr(app)
        else:
            await app.authorize()
    await app.get_me()
    if not app.is_initialized:
        await app.initialize()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--yes', action='store_true',
                        help='skip the final confirmation prompt')
    parser.add_argument('--include-saved', action='store_true',
                        help='also delete everything in Saved Messages')
    parser.add_argument('--leave-groups', action='store_true',
                        help='leave groups and channels unless this account owns them')
    parser.add_argument('--qr', action='store_true',
                        help='use QR login without asking for the login method')
    parser.add_argument('--cleanup-only', action='store_true',
                        help='skip message search and only clear dialogs/groups')
    args = parser.parse_args()

    try:
        await ensure_logged_in(args.qr)
        me = await app.get_me()
        me_id = me.id
        print(f'\nLogged in as {me.first_name} (id {me_id}).')

        print('Listing chats (including archived)...')
        chats = await get_all_chats()
        print(f'{len(chats)} chats found. Scanning for your messages...')

        found = []      # (chat, ids)
        skipped = []    # (chat, reason)
        for chat in ([] if args.cleanup_only else chats):
            if chat.id == me_id:
                if args.include_saved:
                    pass
                else:
                    skipped.append((chat, 'Saved Messages (use --include-saved)'))
                    continue
            try:
                ids = await scan_chat(chat, me_id)
            except Exception as e:
                skipped.append((chat, f'error: {e}'))
                continue
            if ids:
                print(f'  {format_chat(chat)}: {len(ids)} of your messages')
                found.append((chat, ids))

        total = sum(len(ids) for _, ids in found)
        print(f'\n=== SUMMARY: {total} of your messages in {len(found)} chats ===')
        for chat, ids in sorted(found, key=lambda x: -len(x[1])):
            print(f'  {len(ids):>7}  {format_chat(chat)}')
        for chat, reason in skipped:
            print(f'  [skipped] {format_chat(chat)}: {reason}')

        if total and not args.yes:
            print('\nTHIS WILL PERMANENTLY DELETE ALL LISTED MESSAGES '
                  '(revoke=True: gone for both sides). IT CANNOT BE UNDONE.')
            answer = input('Please type "I UNDERSTAND" to proceed: ')
            if answer.upper() != 'I UNDERSTAND':
                print('Better safe than sorry. Aborting...')
                return

        print()
        done = 0
        for chat, ids in found:
            done += await delete_ids(chat, ids)
        print(f'\nDone. Deleted {done}/{total} messages.')
        if args.leave_groups:
            left = deleted = histories = failed = 0
            for chat in chats:
                outcome = await remove_chat(chat)
                if outcome == 'left':
                    left += 1
                    print(f'  Left {format_chat(chat)}')
                elif outcome == 'deleted_owner':
                    deleted += 1
                    print(f'  Deleted owned {format_chat(chat)}')
                elif outcome == 'history_deleted':
                    histories += 1
                    print(f'  Cleared {format_chat(chat)}')
                elif outcome.startswith('error:'):
                    failed += 1
                    print(f'  Could not leave {format_chat(chat)} ({outcome[6:]})')
            print(f'Dialogs: cleared {histories}, groups/channels left {left}, deleted owned {deleted}, failed {failed}.')
    except UnknownError as e:
        print(f'UnknownError occured: {e}')
    finally:
        if app.is_initialized:
            await app.stop()
        elif app.is_connected:
            await app.disconnect()


app.run(main())
