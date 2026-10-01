"""Isolated, cancellable gTTS worker. Text is read from a private file, not argv."""
import sys
from pathlib import Path
from gtts import gTTS


def main():
    source, output, language, tld = sys.argv[1:]
    gTTS(text=Path(source).read_text(encoding='utf-8'), lang=language,
         tld=tld, timeout=(10, 30)).save(output)

if __name__ == '__main__':main()
