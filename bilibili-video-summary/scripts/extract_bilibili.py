"""Extract native Bilibili subtitles or download audio for local transcription."""
import argparse
import hashlib
import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


API_BASE = "https://api.bilibili.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
)
BVID_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
MIXIN_KEY_TABLE = (
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
)


class BilibiliError(RuntimeError):
    pass


def normalize_bvid(value: str) -> str:
    match = BVID_PATTERN.search(value)
    if not match:
        raise BilibiliError("no BV id was found in the source")
    raw = match.group(0)
    return "BV" + raw[2:]


def make_opener(cookie_file: str | None):
    handlers = []
    if cookie_file:
        jar = http.cookiejar.MozillaCookieJar(cookie_file)
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except (OSError, http.cookiejar.LoadError) as exc:
            raise BilibiliError(f"unable to load Netscape cookie file: {exc}") from exc
        handlers.append(urllib.request.HTTPCookieProcessor(jar))
    return urllib.request.build_opener(*handlers)


def request_bytes(opener, url: str, referer: str | None = None, timeout: int = 30):
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with opener.open(request, timeout=timeout) as response:
        return response.read(), response.geturl(), response.headers


def request_json(opener, url: str, referer: str | None = None) -> dict:
    payload, _, _ = request_bytes(opener, url, referer=referer)
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BilibiliError("Bilibili returned a non-JSON response") from exc
    if isinstance(data, dict) and data.get("code") not in (None, 0):
        raise BilibiliError(
            f"Bilibili API error {data.get('code')}: {data.get('message') or data.get('msg')}"
        )
    return data


def resolve_source(opener, source: str) -> tuple[str, str]:
    try:
        return normalize_bvid(source), source
    except BilibiliError:
        pass
    if not re.match(r"^https?://", source, re.IGNORECASE):
        raise BilibiliError("source must be a BV id or an http(s) URL")
    payload, final_url, _ = request_bytes(opener, source)
    candidates = [final_url, payload.decode("utf-8", errors="replace")]
    for candidate in candidates:
        try:
            parsed = urllib.parse.urlsplit(final_url)
            clean_url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, "", "")
            )
            return normalize_bvid(candidate), clean_url
        except BilibiliError:
            continue
    raise BilibiliError("the page did not expose a mounted Bilibili video")


def filename_key(url: str) -> str:
    name = Path(urllib.parse.urlparse(url).path).name
    return name.split(".")[0]


def get_mixin_key(opener) -> str:
    nav = request_json(opener, f"{API_BASE}/x/web-interface/nav")
    wbi = nav["data"]["wbi_img"]
    source = filename_key(wbi["img_url"]) + filename_key(wbi["sub_url"])
    return "".join(source[index] for index in MIXIN_KEY_TABLE)[:32]


def wbi_query(opener, parameters: dict) -> str:
    params = {key: value for key, value in parameters.items() if value is not None}
    params["wts"] = int(time.time())
    filtered = {}
    for key, value in params.items():
        filtered[key] = re.sub(r"[!'()*]", "", str(value))
    query = urllib.parse.urlencode(sorted(filtered.items()))
    signature = hashlib.md5((query + get_mixin_key(opener)).encode()).hexdigest()
    return f"{query}&w_rid={signature}"


def api_view(opener, bvid: str) -> dict:
    query = urllib.parse.urlencode({"bvid": bvid})
    return request_json(opener, f"{API_BASE}/x/web-interface/view?{query}")["data"]


def player_info(opener, aid: int, cid: int, referer: str) -> tuple[dict, str]:
    try:
        query = wbi_query(opener, {"aid": aid, "cid": cid})
        data = request_json(
            opener, f"{API_BASE}/x/player/wbi/v2?{query}", referer
        )["data"]
        return data, "wbi_v2"
    except BilibiliError as wbi_error:
        query = urllib.parse.urlencode({"aid": aid, "cid": cid})
        try:
            data = request_json(opener, f"{API_BASE}/x/player/v2?{query}", referer)[
                "data"
            ]
            return data, "public_v2_fallback"
        except BilibiliError:
            raise wbi_error


def choose_subtitle(tracks: list[dict], preferences: list[str]) -> dict | None:
    if not tracks:
        return None
    for preference in preferences:
        lowered = preference.lower()
        for track in tracks:
            language = str(track.get("lan", "")).lower()
            if language == lowered or language.startswith(lowered + "-"):
                return track
    return tracks[0]


def subtitle_url(track: dict) -> str:
    url = track.get("subtitle_url") or track.get("subtitleUrl")
    if not url:
        raise BilibiliError("the selected subtitle track has no download URL")
    return "https:" + url if url.startswith("//") else url


def subtitle_lines(body: list[dict]) -> list[str]:
    lines = []
    for row in body:
        content = str(row.get("content", "")).strip()
        if not content:
            continue
        start = float(row.get("from", 0))
        end = float(row.get("to", start))
        lines.append(f"[{start:010.3f} - {end:010.3f}] {content}")
    return lines


def playurl(opener, bvid: str, cid: int, referer: str) -> tuple[dict, str]:
    parameters = {"bvid": bvid, "cid": cid, "fnval": 16, "qn": 0, "fourk": 1}
    try:
        query = wbi_query(opener, parameters)
        data = request_json(
            opener, f"{API_BASE}/x/player/wbi/playurl?{query}", referer
        )["data"]
        return data, "wbi_playurl"
    except BilibiliError as wbi_error:
        query = urllib.parse.urlencode(parameters)
        try:
            data = request_json(
                opener, f"{API_BASE}/x/player/playurl?{query}", referer
            )["data"]
            return data, "public_playurl_fallback"
        except BilibiliError:
            raise wbi_error


def download_audio(opener, play_data: dict, destination: Path, referer: str) -> dict:
    audio_tracks = (play_data.get("dash") or {}).get("audio") or []
    if not audio_tracks:
        raise BilibiliError("playback data contains no downloadable audio track")
    selected = max(audio_tracks, key=lambda item: int(item.get("bandwidth", 0)))
    url = selected.get("baseUrl") or selected.get("base_url")
    if not url:
        raise BilibiliError("selected audio track has no URL")
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Referer": referer}
    request = urllib.request.Request(url, headers=headers)
    temporary = destination.with_suffix(destination.suffix + ".part")
    total = 0
    response_content_type = None
    try:
        with opener.open(request, timeout=120) as response, temporary.open("wb") as stream:
            response_content_type = response.headers.get_content_type()
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
                total += len(chunk)
        if total == 0:
            raise BilibiliError("downloaded audio is empty")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "file": destination.name,
        "bytes": total,
        "bandwidth": selected.get("bandwidth"),
        "mime_type": selected.get("mimeType") or response_content_type,
    }


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_failure(directory: Path, stage: str, reason: str, attempted: list[str]):
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": stage,
        "reason": reason,
        "attempted_methods": attempted,
        "suggested_action": "检查登录状态和网络后，只重试该视频一次。",
    }
    write_json(directory / "failures.json", payload)


def safe_error(exc: Exception) -> str:
    message = URL_PATTERN.sub("<redacted-url>", str(exc))
    return f"{type(exc).__name__}: {message[:500]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="BV id, video URL, b23 short URL, or dynamic URL")
    parser.add_argument("--output-root", default="outputs")
    parser.add_argument("--page", type=int, default=1, help="1-based multipart page")
    parser.add_argument(
        "--language",
        action="append",
        dest="languages",
        help="Preferred native subtitle language; may be repeated.",
    )
    parser.add_argument("--cookie-file", help="Netscape-format cookie file; never copied")
    parser.add_argument("--download-audio", action="store_true")
    args = parser.parse_args()

    opener = make_opener(args.cookie_file)
    bvid, resolved_source = resolve_source(opener, args.source)
    output = Path(args.output_root) / bvid
    subtitles_dir = output / "subtitles"
    output.mkdir(parents=True, exist_ok=True)
    subtitles_dir.mkdir(parents=True, exist_ok=True)
    attempted = ["resolve_source", "video_view"]

    try:
        view = api_view(opener, bvid)
        pages = view.get("pages") or []
        if args.page < 1 or args.page > len(pages):
            raise BilibiliError(
                f"page {args.page} is outside the available range 1..{len(pages)}"
            )
        page = pages[args.page - 1]
        aid = int(view["aid"])
        cid = int(page["cid"])
        referer = f"https://www.bilibili.com/video/{bvid}"
        attempted.append("native_subtitle_api")
        player, player_api = player_info(opener, aid, cid, referer)
        tracks = ((player.get("subtitle") or {}).get("subtitles") or [])
        preferences = args.languages or ["zh-CN", "zh-Hans", "zh-Hant", "ai-zh", "zh", "en"]
        track = choose_subtitle(tracks, preferences)
        owner = view.get("owner") or {}
        metadata = {
            "bvid": bvid,
            "aid": aid,
            "cid": cid,
            "page": args.page,
            "title": view.get("title") or bvid,
            "owner": owner.get("name"),
            "duration_seconds": page.get("duration") or view.get("duration"),
            "source_url": resolved_source,
            "status": "extracting",
            "subtitle_source": None,
            "player_api": player_api,
            "output_directory": bvid,
        }

        if track:
            payload = request_json(opener, subtitle_url(track), referer)
            body = payload.get("body") or []
            lines = subtitle_lines(body)
            if not lines:
                raise BilibiliError("native subtitle track exists but its body is empty")
            raw_path = subtitles_dir / "raw.txt"
            raw_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            write_json(subtitles_dir / "native.json", payload)
            metadata.update(
                {
                    "status": "extracted",
                    "subtitle_source": "native",
                    "subtitle_language": track.get("lan"),
                    "raw_subtitle": "subtitles/raw.txt",
                    "native_subtitle": "subtitles/native.json",
                    "subtitle_lines": len(lines),
                }
            )
        elif args.download_audio:
            attempted.append("signed_audio_download")
            play_data, play_api = playurl(opener, bvid, cid, referer)
            audio_info = download_audio(
                opener,
                play_data,
                output / "audio.m4s",
                referer,
            )
            audio_info["play_api"] = play_api
            metadata.update(
                {
                    "status": "needs_transcription",
                    "subtitle_source": None,
                    "audio": audio_info,
                }
            )
        else:
            metadata.update(
                {
                    "status": "needs_transcription",
                    "subtitle_source": None,
                    "next_action": "rerun with --download-audio",
                }
            )
        write_json(output / "metadata.json", metadata)
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
    except Exception as exc:
        write_failure(output, "extraction", safe_error(exc), attempted)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
