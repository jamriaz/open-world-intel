"""Fully automatic YouTube channel pipeline: unofficial GTA fan channel (English), stock footage only.
Modes:  python main.py short   -> 9:16 Short, about 40 seconds
        python main.py long    -> 16:9 video, about 8-9 minutes, with thumbnail
Topic -> script -> voice -> stock clips -> captions -> upload (private).
"""
import os, sys, json, random, asyncio, subprocess, time, pathlib
import requests
import edge_tts

ROOT = pathlib.Path(__file__).parent
WORK = ROOT / "work"
USED = ROOT / "used_topics.json"

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
MODE = (os.environ.get("MODE") or (ARGS[0] if ARGS else "short")).strip().lower()
if MODE not in ("short", "long"):
    MODE = "short"
LONG = MODE == "long"
DRY_RUN = os.environ.get("DRY_RUN") == "1" or "--dry" in sys.argv


def read_key(env_name, file_name):
    if os.environ.get(env_name):
        return os.environ[env_name].strip()
    p = ROOT / file_name
    if p.exists():
        return p.read_text().strip()
    sys.exit(f"Key nahi mili: {file_name} file banao (us mein sirf key paste karo)")


GEMINI_KEY = read_key("GEMINI_API_KEY", "gemini_key.txt")
PIXABAY_KEY = read_key("PIXABAY_API_KEY", "pixabay_key.txt")
MODEL = os.environ.get("GEMINI_MODEL", "")
FAST_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash",
               "gemini-3.6-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
SMART_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-flash-latest",
                "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
VOICE = os.environ.get("TTS_VOICE") or "en-US-GuyNeural"  # energetic male news voice
VOICE_PITCH = os.environ.get("TTS_PITCH", "-3Hz")
VOICE_RATE = os.environ.get("TTS_RATE", "+4%")
PRIVACY = os.environ.get("PRIVACY", "private")  # public karna ho to PRIVACY=public
FONT = "Arial" if os.name == "nt" else "DejaVu Sans"
W, H = (1280, 720) if LONG else (1080, 1920)


def run(cmd):
    r = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{r.stderr[-1500:]}")
    return r.stdout


# ---------- 1. topic + research + script ----------
def gemini(prompt, smart=False, search=False, as_json=True):
    gc = {"temperature": 0.9 if as_json else 0.2, "maxOutputTokens": 12000 if smart else 4000}
    if as_json:
        gc["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gc}
    if search:
        body["tools"] = [{"google_search": {}}]
    models = [MODEL] if MODEL else []
    models += [m for m in (SMART_MODELS if (smart or search) else FAST_MODELS) if m not in models]
    last = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        for i in range(3):
            try:
                r = requests.post(url, json=body, timeout=300)
            except requests.exceptions.RequestException as e:
                last = f"{model}: {type(e).__name__}"
                print("Gemini network problem ->", last, flush=True)
                time.sleep(5)
                if i >= 1:
                    break
                continue
            if r.status_code == 200:
                try:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    text = "".join(p.get("text", "") for p in parts)
                    return json.loads(text) if as_json else text
                except Exception as e:
                    last = f"{model}: bad response ({e})"
                    time.sleep(3)
                    continue
            last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
            print("Gemini problem ->", last, flush=True)
            if r.status_code in (400, 401, 403, 404, 429):
                break
            time.sleep(5 * (i + 1))
    raise RuntimeError("Koi bhi Gemini model nahi chala. Aakhri error: " + last)


# (content type, weight, needs fresh web research)
KINDS = [
    ("GTA 6 guides, tips and how things work, using only officially confirmed or well-reported information", 3, True),
    ("what Rockstar has officially shown of GTA 6: world, map, characters, vehicles, activities (official info only)", 3, True),
    ("GTA series history and little-known facts (GTA III, Vice City, San Andreas, IV, V, Online): long-established facts", 3, False),
    ("GTA 5 vs GTA 6 comparisons using only officially confirmed facts", 2, True),
    ("real-world places, events and culture that inspired the GTA games", 1, False),
    ("how the GTA games were made: development and release history", 1, False),
]

RULES = """- Facts: use ONLY the research notes for anything about GTA 6 or other current news. If something is marked UNCONFIRMED or sources disagree, either skip it or say clearly that Rockstar has not confirmed it. Never invent features, dates, prices, numbers or quotes.
- No leaks, no spoilers: nothing about the story, characters' fates, endings or mission reveals, and never describe leaked or unreleased footage.
- Clean content: no hate, no politics, no real-person gossip, no instructions for real-world crime.
- We cannot show real game footage, so for every scene give 1-3 word English stock-video keywords that match the mood (examples: "miami skyline", "neon city night", "sports car driving", "police lights", "palm trees beach", "speedboat ocean", "helicopter city", "night traffic", "swamp", "gaming controller", "retro arcade", "city map"). Avoid keywords that return people or faces."""

TITLE_RULES = """Title rules: include "GTA 6" (or the specific GTA game) near the start. Use a concrete number, a clear promise or a question people search for. No hashtags. Never use hype words like "Shocking", "Insane", "You won't believe" and never claim something is "confirmed" unless the notes say so. It must be 100% honest to the content.
thumb_text rules: 2 to 4 words, ALL CAPS, maximum 22 characters, a curiosity hook that does NOT repeat the title word for word (examples: "WHAT WE KNOW", "5 BIG CHANGES", "HIDDEN DETAIL?")."""

DISCLAIMER = ("Unofficial fan channel. Not affiliated with, endorsed by or sponsored by Rockstar Games or Take-Two Interactive. "
              "Visuals are generic royalty-free stock footage, not game footage. Grand Theft Auto is a trademark of Take-Two Interactive.")


def pick_topic(kind, used):
    avoid = ", ".join(used[-300:]) or "none"
    prompt = f"""You plan videos for an unofficial GTA fan channel for English speakers.
Content type: {kind}.
Pick ONE specific topic that people really search for (examples: "How the wanted system could work in GTA 6", "10 GTA San Andreas secrets almost nobody knew", "Every vehicle type Rockstar has shown for GTA 6").
Do NOT repeat or closely repeat these past topics: {avoid}
Return JSON: {{"topic": "the topic in 4 to 10 words"}}"""
    return str(gemini(prompt)["topic"]).strip()


def research(topic):
    prompt = f"""Use Google Search. Collect verified, current facts for a YouTube video about: "{topic}" (Grand Theft Auto series).
Return 15 to 25 short bullet facts. After each fact add (source site, date if known).
Only include officially confirmed information or facts reported by several reputable outlets. Exclude leaks, rumours, spoilers, story endings and descriptions of unreleased footage. If something is unconfirmed, start that bullet with UNCONFIRMED:.
Plain text only, no introduction."""
    try:
        text = gemini(prompt, search=True, as_json=False)
        if text and len(text) > 300:
            return text.strip()
    except Exception as e:
        print("Research nahi chali:", e, flush=True)
    return None


def make_script(used):
    kind = needs = topic = notes = None
    for attempt in range(2):
        pool = KINDS if attempt == 0 else [k for k in KINDS if not k[2]]
        kind, _w, needs = random.choices(pool, [k[1] for k in pool])[0]
        topic = pick_topic(kind, used)
        print("Topic idea:", topic, flush=True)
        notes = research(topic)
        if notes or not needs:
            break
        print("Research nahi mili, history topic par ja rahe hain", flush=True)
    if notes:
        notes_block = "RESEARCH NOTES (the only source you may use for current facts):\n" + notes
    else:
        notes_block = ("NO RESEARCH NOTES AVAILABLE. Use only long-established facts about GTA III, Vice City, San Andreas, "
                       "GTA IV and GTA V. Do not mention any GTA 6 features.")
    if LONG:
        prompt = f"""You write scripts for an unofficial GTA fan YouTube channel. Audience: English speakers of all ages worldwide. Topic: "{topic}".
{notes_block}

Write a clear, engaging explainer of 1200 to 1400 spoken words (about 8 to 9 minutes).
- The very first sentence (maximum 12 words) must be a striking claim, number or question that opens a curiosity loop. Never start with "Imagine", "Welcome" or "In this video". Within the first 30 seconds promise the payoff and tease a twist you reveal later.
- Then 10 clear sections, each building curiosity and ending with a small twist into the next. Every two sections add a re-hook such as "But here is the part nobody expects."
- Conversational, easy words, short sentences, no filler, no repeating yourself.
- Final scene: sum up the big idea, ask one question for the comments, say "If you enjoyed this, subscribe and I'll see you in the next one."
{RULES}
- Split into exactly 14 scenes of roughly equal length (80 to 110 words each). Each scene gets exactly 3 keywords.

{TITLE_RULES}

Return JSON:
{{"topic": "{topic}", "title": "YouTube title, 40 to 65 characters", "thumb_text": "...",
"scenes": [{{"text": "...", "keywords": ["...", "...", "..."]}}],
"description": "3 to 4 sentences describing the video for viewers", "tags": ["12 relevant tags including gta 6"],
"sources": ["names of the news sites used in the notes, up to 5"]}}"""
    else:
        prompt = f"""You write viral YouTube Shorts for an unofficial GTA fan channel, for English speakers worldwide. Topic: "{topic}".
{notes_block}

- Spoken text 70 to 95 words (about 30 to 38 seconds). Fast, punchy, curious tone. Every sentence short.
- First sentence is a scroll-stopping hook of at most 10 words (a number, a surprising claim or a question). Never start with "Did you know", "Today" or "Imagine".
- 3 or 4 interesting facts, each stronger than the last.
- Last scene: end with a sentence that flows naturally back into the first sentence so the Short loops, then one very short question for the comments. No "Follow for more".
{RULES}
- Split into exactly 6 scenes. Each scene gets exactly 1 keyword.

{TITLE_RULES}

Return JSON:
{{"topic": "{topic}", "title": "title, 30 to 55 characters", "thumb_text": "...",
"scenes": [{{"text": "...", "keywords": ["..."]}}],
"description": "2 short sentences about the video", "tags": ["8 relevant tags including gta 6"],
"sources": ["names of the news sites used in the notes, up to 3"]}}"""
    for attempt in range(3):
        data = gemini(prompt, smart=LONG)
        for sc in data["scenes"]:
            kws = sc.get("keywords") or ([sc["keyword"]] if sc.get("keyword") else [])
            sc["keywords"] = [k for k in kws if k] or ["neon city night"]
        words = sum(len(x["text"].split()) for x in data["scenes"])
        need = 900 if LONG else 60
        if len(data["scenes"]) >= 4 and words >= need:
            data["topic"] = topic
            data["sources"] = [str(x) for x in data.get("sources", [])][:5]
            print(f"Script ok: {words} words, {len(data['scenes'])} scenes, notes={'yes' if notes else 'no'}", flush=True)
            return data
        print(f"Script too short ({words} words), retry {attempt + 1}", flush=True)
    raise RuntimeError("Gemini script bahut chhoti aayi, dobara try karo.")


# ---------- 2. voice ----------
async def _tts(text, mp3):
    attempts = [
        dict(rate=VOICE_RATE, pitch=VOICE_PITCH, boundary="WordBoundary"),
        dict(rate=VOICE_RATE, pitch=VOICE_PITCH),
        dict(boundary="WordBoundary"),
        dict(),
    ]
    last = None
    for kw in attempts:
        try:
            comm = edge_tts.Communicate(text, VOICE, **kw)
            words = []
            with open(mp3, "wb") as f:
                async for ch in comm.stream():
                    if ch["type"] == "audio":
                        f.write(ch["data"])
                    elif ch["type"] == "WordBoundary":
                        st = ch["offset"] / 1e7
                        words.append((st, st + ch["duration"] / 1e7, ch["text"]))
            if words:
                return words
            last = "no word timings"
        except Exception as e:
            last = e
            print("TTS option failed, trying simpler:", kw, "->", e, flush=True)
    raise RuntimeError(f"TTS nahi chali: {last}")


def audio_len(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path])
    return float(out.strip())


# ---------- 3. clips ----------
BAD_TAGS = {"woman", "women", "girl", "girls", "man", "men", "people", "model", "bikini", "swimsuit",
            "swimwear", "lingerie", "beach girl", "sexy", "fashion", "party", "crowd", "person", "lady"}


def clip_ok(hit, keyword):
    tags = {t.strip().lower() for t in hit.get("tags", "").split(",")}
    allowed = set(keyword.lower().split())
    if (tags & BAD_TAGS) - allowed:
        return False
    if LONG:
        v = hit["videos"].get("medium") or hit["videos"].get("small") or {}
        if v.get("width") and v.get("height") and v["width"] < v["height"]:
            return False
    return True


def find_clip(keyword, used_ids):
    for q in (keyword, keyword.split()[-1], "city night", "neon"):
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": PIXABAY_KEY, "q": q, "per_page": 40, "safesearch": "true"},
            timeout=30,
        )
        hits = r.json().get("hits", [])
        random.shuffle(hits)
        for h in hits:
            if h["id"] in used_ids or not clip_ok(h, keyword):
                continue
            v = h["videos"]
            for size in ("medium", "small", "large", "tiny"):
                if v.get(size, {}).get("url"):
                    return h["id"], v[size]["url"]
    raise RuntimeError(f"no clip for {keyword}")


def download(url, path):
    for i in range(3):
        try:
            r = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            pathlib.Path(path).write_bytes(r.content)
            return
        except requests.exceptions.RequestException as e:
            print("Download problem, retry:", type(e).__name__, flush=True)
            if i == 2:
                raise
            time.sleep(4)


# ---------- 4. captions (Shorts and long) ----------
def ts(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def make_ass(words, path, hook=None):
    if LONG:  # chhote safed captions, neeche
        size, per, margin, color, outline, upper = 50, 6, 45, "&H00FFFFFF", 4, False
    else:     # bade peele captions, Shorts
        size, per, margin, color, outline, upper = 96, 3, 420, "&H0000FFFF", 9, True
    fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
           "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
           "MarginR, MarginV, Encoding")
    style = f"Style: Default,{FONT},{size},{color},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},3,2,60,60,{margin},1"
    hook_style = f"Style: Hook,{FONT},118,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,10,3,8,70,70,230,1"
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\n\n[V4+ Styles]\n{fmt}\n{style}\n{hook_style}\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = []
    if hook and not LONG:  # pehle 3 second ka bada hook text (Shorts retention)
        h = hook.upper().replace("{", "").replace("}", "")
        lines.append(f"Dialogue: 1,{ts(0)},{ts(3.0)},Hook,,0,0,0,,{{\\fad(120,350)}}{h}")
    n = len(words)
    for i in range(0, n, per):
        chunk = words[i:i + per]
        start = chunk[0][0]
        end = words[i + per][0] if i + per < n else chunk[-1][1] + 0.3
        text = " ".join(w[2] for w in chunk).replace("{", "").replace("}", "")
        if upper:
            text = text.upper()
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{text}")
    pathlib.Path(path).write_text(head + "\n".join(lines), encoding="utf-8")


# ---------- 5. thumbnail (long videos) ----------
def make_thumb(title, hook=None, out_name="thumb.jpg"):
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageEnhance
        run(["ffmpeg", "-y", "-ss", "1", "-i", "seg0.mp4", "-frames:v", "1", "-q:v", "2", "thumb_raw.jpg"])
        im = Image.open(WORK / "thumb_raw.jpg").convert("RGB").resize((1280, 720))
        im = ImageEnhance.Color(im).enhance(1.4)
        im = ImageEnhance.Contrast(im).enhance(1.2)
        # neon pink/purple tint on the right, dark purple gradient on the left for the text
        tint = Image.new("RGB", (1280, 720), (255, 70, 170))
        tmask = Image.new("L", (1280, 720), 0)
        td = ImageDraw.Draw(tmask)
        for x in range(1280):
            td.line([(x, 0), (x, 720)], fill=int(70 * x / 1280))
        im = Image.composite(tint, im, tmask)
        grad = Image.new("L", (1280, 720), 0)
        gd = ImageDraw.Draw(grad)
        for x in range(0, 900):
            gd.line([(x, 0), (x, 720)], fill=int(225 * (1 - x / 900) ** 1.2))
        im = Image.composite(Image.new("RGB", (1280, 720), (24, 4, 52)), im, grad)
        d = ImageDraw.Draw(im)
        text = (hook or " ".join(title.split()[:4])).upper().strip()
        path = next((p for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                                 "C:/Windows/Fonts/arialbd.ttf") if os.path.exists(p)), None)
        maxw, words_, chosen = 780, text.split(), None
        for size in (170, 150, 132, 116, 100, 88, 76):
            font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
            if any(d.textlength(w, font=font) > maxw for w in words_):
                continue
            lines, cur = [], ""
            for w in words_:
                test = (cur + " " + w).strip()
                if d.textlength(test, font=font) > maxw and cur:
                    lines.append(cur)
                    cur = w
                else:
                    cur = test
            lines.append(cur)
            if len(lines) <= 3:
                chosen = (size, font, lines)
                break
        if not chosen:
            font = ImageFont.truetype(path, 76) if path else ImageFont.load_default()
            chosen = (76, font, [text])
        size, font, lines = chosen
        step = int(size * 1.12)
        y = (720 - len(lines) * step) // 2
        for i, ln in enumerate(lines):
            d.text((60, y + i * step), ln, font=font, fill="#4DF3FF" if i == len(lines) - 1 else "#FFFFFF",
                   stroke_width=max(7, size // 11), stroke_fill="#14002B")
        im.save(WORK / out_name, quality=92)
        return WORK / out_name
    except Exception as e:
        print("Thumbnail nahi bani (zaroori nahi):", e, flush=True)
        return None


# ---------- 6. build video ----------
def build_video(data, out_name):
    WORK.mkdir(exist_ok=True)
    scenes = data["scenes"]
    full_text = " ".join(s["text"] for s in scenes)
    words = asyncio.run(_tts(full_text, str(WORK / "voice.mp3")))
    dur = audio_len("voice.mp3")
    print(f"Voice {VOICE} ({VOICE_PITCH}, {VOICE_RATE}): {dur:.0f} seconds", flush=True)
    make_ass(words, WORK / "captions.ass", data.get("thumb_text"))

    counts = [len(s["text"].split()) for s in scenes]
    total, n = sum(counts), len(words)
    ends, cum = [], 0
    for c in counts:
        cum += c
        idx = min(n - 1, max(0, round(cum / total * n) - 1))
        ends.append(words[idx][1])
    ends[-1] = dur + 0.4

    used_ids, start, parts = set(), 0.0, []
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1"
    k = 0
    for sc, end in zip(scenes, ends):
        length = max(1.5, end - start)
        start = end
        kws = sc["keywords"]
        piece = max(2.0, length / len(kws))
        remaining = length
        for j, kw in enumerate(kws):
            seg_len = remaining if j == len(kws) - 1 else min(piece, remaining)
            if seg_len < 0.3:
                continue
            remaining -= seg_len
            cid, url = find_clip(kw, used_ids)
            used_ids.add(cid)
            raw, seg = f"raw{k}.mp4", f"seg{k}.mp4"
            download(url, WORK / raw)
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", raw, "-t", f"{seg_len:.2f}", "-vf", vf,
                 "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", seg])
            (WORK / raw).unlink(missing_ok=True)
            parts.append(seg)
            k += 1

    (WORK / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-i", "voice.mp3",
         "-vf", "ass=captions.ass", "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", out_name])
    return WORK / out_name


# ---------- 7. upload ----------
def upload(path, data, thumb=None):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    token = ROOT / "token.json"
    if os.environ.get("YT_TOKEN_JSON"):
        creds = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"]), scopes)
    elif token.exists():
        creds = Credentials.from_authorized_user_file(str(token), scopes)
    else:
        sys.exit("token.json nahi mili. Pehle get_token.py chalao.")
    yt = build("youtube", "v3", credentials=creds)
    srcs = ("Sources: " + ", ".join(data.get("sources", [])) + "\n\n") if data.get("sources") else ""
    if LONG:
        title = data["title"][:100]
        desc = data["description"] + "\n\n" + srcs + DISCLAIMER + "\n\n#gta6 #gta #gaming #grandtheftauto"
    else:
        title = data["title"][:80]
        if "#shorts" not in title.lower() and len(title) < 90:
            title += " #shorts"
        desc = data["description"] + "\n\n" + srcs + DISCLAIMER + "\n\n#shorts #gta6 #gta #gaming"
    body = {
        "snippet": {"title": title, "description": desc, "tags": data["tags"][:15], "categoryId": "20",
                    "defaultLanguage": "en", "defaultAudioLanguage": "en"},
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(path), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if thumb:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
        except Exception as e:
            print("Thumbnail upload nahi hui (channel phone-verified hona chahiye):", e, flush=True)
    return vid


def main():
    used = json.loads(USED.read_text()) if USED.exists() else []
    print("MODE:", MODE, flush=True)
    data = make_script(used)
    print("Topic:", data["topic"], "|", data["title"], flush=True)
    video = build_video(data, "final.mp4")
    thumb = make_thumb(data["title"], data.get("thumb_text")) if LONG else None
    if DRY_RUN:
        print("DRY_RUN: video ready at", video, flush=True)
    else:
        vid = upload(video, data, thumb)
        print("Uploaded:", ("https://youtu.be/" if LONG else "https://youtube.com/shorts/") + vid, flush=True)
    used.append(data["topic"].lower())
    USED.write_text(json.dumps(used, indent=1))


if __name__ == "__main__":
    main()
