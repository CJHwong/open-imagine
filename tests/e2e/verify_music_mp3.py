"""A song leaves Music as a tagged MP3, and keeps the WAV when the encoder is absent.

uv run --with playwright python tests/e2e/verify_music_mp3.py <port>
Run against a fresh `uv run studio --stub --port <port>`. No model is loaded.
"""

import base64
import io
import sys
import wave

from playwright.sync_api import expect, sync_playwright

STYLE = "Use a pop arrangement with a memorable melodic hook and clear verse and chorus sections over a steady pulse."


def recording():
    source = io.BytesIO()
    with wave.open(source, "wb") as song:
        song.setnchannels(2)
        song.setsampwidth(2)
        song.setframerate(48000)
        song.writeframes(b"\x00\x01\x00\x00" * 48000)
    return source.getvalue()


def add_song(page, blob):
    page.evaluate(
        """async ({encoded, style}) => {
          const studio = document.querySelector('music-studio');
          await studio.setKeeping(false);
          const blob = new Blob([Uint8Array.from(atob(encoded), value => value.charCodeAt(0))],
            {type: 'audio/wav'});
          studio.songs = [{id: 'mp3-a', title: 'Morning Test', blob, seconds: 1, seed: 5,
            createdAt: Date.UTC(2026, 0, 2), score: '', settings: {style},
            model: 'YuE2 (MLX Q8)', metadata: {}}];
          studio.selectedId = 'mp3-a';
          studio.renderSongs();
        }""",
        {"encoded": base64.b64encode(blob).decode(), "style": STYLE},
    )


def frames(tag):
    out, offset = {}, 0
    while offset + 10 <= len(tag) and tag[offset : offset + 4] != b"\x00\x00\x00\x00":
        name = tag[offset : offset + 4].decode("latin-1")
        size = int.from_bytes(tag[offset + 4 : offset + 8], "big")
        out[name] = tag[offset + 10 : offset + 10 + size]
        offset += 10 + size
    return out


def text(body):
    return body[3:].decode("utf-16-le") if body[:3] == b"\x01\xff\xfe" else body[1:].decode("latin-1")


def main():
    base = f"http://127.0.0.1:{int(sys.argv[1])}"
    blob = recording()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?workspace=music")
        page.wait_for_function("Boolean(document.querySelector('music-studio').capabilities)")
        add_song(page, blob)
        bar = page.locator(".music-output-details:not([hidden])")
        with page.expect_download(timeout=30000) as download:
            bar.get_by_role("button", name="Download MP3", exact=True).click()
        saved = download.value
        data = saved.path().read_bytes()
        assert saved.suggested_filename == "music-5.mp3", saved.suggested_filename
        assert data[:3] == b"ID3" and data[3] == 3 and data[4] == 0, data[:6]
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        tag = data[10 : 10 + size]
        found = frames(tag)
        assert text(found["TIT2"]) == "Morning Test", text(found["TIT2"])
        assert text(found["TCON"]) == "Pop", text(found["TCON"])
        assert text(found["TYER"]) == "2026", text(found["TYER"])
        assert text(found["TPE1"]) == "YuE2 (MLX Q8)", text(found["TPE1"])
        assert text(found["TLEN"]) == "1000", text(found["TLEN"])
        assert found["COMM"][1:4] == b"eng", found["COMM"][:4]
        assert found["COMM"][4:10] == b"\xff\xfe\x00\x00\xff\xfe", found["COMM"][:10]
        assert "Use a pop arrangement" in found["COMM"][10:].decode("utf-16-le"), found["COMM"][10:40]
        audio = data[10 + size :]
        assert audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0, audio[:4]
        print(
            "PASS MP3 download: ID3v2.3 tags for title, genre, year, artist, length and style, "
            "one MPEG frame after the tag, .mp3 name.",
            flush=True,
        )

        offline = browser.new_context()
        offline_page = offline.new_page()
        offline_page.route("**/vendor/lame.min.js", lambda route: route.abort())
        offline_page.goto(base + "/?workspace=music")
        offline_page.wait_for_function("Boolean(document.querySelector('music-studio').capabilities)")
        add_song(offline_page, blob)
        with offline_page.expect_download(timeout=30000) as fallback:
            offline_page.locator(".music-output-details:not([hidden])").get_by_role(
                "button", name="Download MP3", exact=True
            ).click()
        assert fallback.value.suggested_filename == "music-5.wav", fallback.value.suggested_filename
        expect(offline_page.locator("#toasts")).to_contain_text("MP3 encoder")
        print("PASS MP3 fallback: an unreachable encoder leaves the WAV and says why.", flush=True)

        assert errors == [], errors
        offline.close()
        browser.close()


if __name__ == "__main__":
    main()
