"""English command reference, available without an AI request."""
from .parser import LANGS


def is_help_command(text):
    return (text or '').strip().lower() == '.h'


def help_text(owner=False):
    text = """Little K — Help

.h — Show this command reference in English. .H also works.

.t [language] — Translate text, or choose the language of Little K's answer when your message contains a question or task.
Example: Good night .t zh
Example: .t zh What is 5 + 5?
Without a language: Spanish → Chinese; Chinese → Spanish; other languages → Spanish.
Reply to any message with .t or .t en to translate that message. For Little K's own recorded replies, the translation is added to the original message when editing is possible; otherwise it is sent separately.

.c [request] — Send a text answer and also read it aloud in the active voice chat of this group. Little K joins as its own participant and leaves after inactivity. It never creates a call automatically. Voice playback requires a group, an active call, and permission to speak.
Example: .c Tell me something interesting.
Reply with .c to read the quoted message aloud.

Combine shortcuts: .t zh .c What is the weather today in Monterrey?
You can reverse their order. .tzh and .t.zh also work. Shortcuts are case-insensitive.

Natural language works too: Little K, answer in Chinese and read it in the call.
In allowed private chats, just write normally. In allowed groups, mention Little K, start with “Little K,”, reply to it, or use a shortcut.

Language codes: """ + ', '.join(sorted(LANGS)) + ".\nCommon codes: es Spanish, en English, zh Chinese, ja Japanese, ko Korean, fr French, de German, pt Portuguese, it Italian. Voice playback also needs a configured voice for the chosen language."
    if owner:
        text += """

Owner-only commands
/k status — Check Telegram, Hermes, and voice status.
/k new — Start a new conversation for this chat/topic.
/k voice status — Show whether Little K is connected, playing, or has queued audio.
/k voice stop — Stop playback, clear queued audio, and leave this group's call.
/k voice clear — Clear waiting audio; the current playback continues.
/k reload — Reload access lists and settings. Identity or credential changes require a service restart."""
    else:
        text += "\n\nAdministrative commands are available only to the owner."
    text += "\n\nAccess is limited to allowed chats/users. Where Telegram supports identifiable flag reactions, 🇬🇧 and 🇨🇳 on Little K's replies can request English or Chinese translations. Reply + .t is the reliable alternative."
    return text
