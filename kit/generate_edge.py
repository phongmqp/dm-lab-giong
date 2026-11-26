#!/usr/bin/env python3
"""Tạo giọng đọc MIỄN PHÍ, không cần API key, bằng giọng nơ-ron của Microsoft (HoaiMy / NamMinh).
Đây là cùng loại giọng "Natural" mà Microsoft Edge dùng khi đọc to.

Chạy trên máy có internet (hoặc Google Colab, xem file colab_tao_giong.ipynb):
  pip install edge-tts
  python generate_edge.py                       # tạo tất cả vào thư mục audio/
  python generate_edge.py --only m13-learn      # thử một phần
  python generate_edge.py --voice vi-VN-NamMinhNeural
Cần ffmpeg để ghép file (không có vẫn chạy, chất lượng ghép kém hơn một chút).
"""
import argparse, asyncio, glob, json, os, shutil, subprocess, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
LIMIT = 2800   # ký tự mỗi lần gọi

def voice_for(text):
    """Mai nói cao hơn một chút, chị Hạnh trầm hơn một chút."""
    if text.startswith("Mai nói"): return "+8Hz"
    if text.startswith("Chị Hạnh nói"): return "-6Hz"
    return "+0Hz"

def make_chunks(paras):
    chunks, cur, start, size, pitch = [], [], 0, 0, None
    for i, p in enumerate(paras):
        pt = voice_for(p)
        if cur and (pt != pitch or size + len(p) + 2 > LIMIT):
            chunks.append((start, i - 1, "\n\n".join(cur), pitch)); cur, size, start = [], 0, i
        pitch = pt; cur.append(p); size += len(p) + 2
    if cur: chunks.append((start, len(paras) - 1, "\n\n".join(cur), pitch))
    return chunks

def probe(path):
    if shutil.which("ffprobe"):
        try:
            return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True).strip())
        except Exception: pass
    return os.path.getsize(path) / 6000.0   # ước lượng 48 kbps

async def synth(text, path, voice, rate, pitch, fake):
    if fake:   # chế độ thử: tạo âm thanh im lặng, chỉ để kiểm tra quy trình
        secs = max(2, len(text) / 15.0)
        subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(secs), "-b:a", "32k", path]); return
    import edge_tts
    for attempt in range(6):
        try:
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)
            if os.path.getsize(path) > 1000: return
        except Exception as e:
            err = e
        await asyncio.sleep(2 * (attempt + 1))
    sys.exit(f"Không tạo được giọng (kiểm tra mạng). Lỗi cuối: {err}")

async def run(a):
    keys = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(HERE, "scripts", "*.txt")))
    if a.only: keys = [k for k in keys if a.only in k]
    os.makedirs(os.path.join(HERE, "audio"), exist_ok=True)
    sem = asyncio.Semaphore(a.parallel)
    for k in keys:
        out_mp3, out_json = (os.path.join(HERE, "audio", k + e) for e in (".mp3", ".json"))
        if os.path.exists(out_mp3) and os.path.exists(out_json):
            print("bỏ qua (đã có):", k); continue
        paras = [p for p in open(os.path.join(HERE, "scripts", k + ".txt"), encoding="utf-8").read().split("\n\n") if p.strip()]
        chunks = make_chunks(paras)
        tmp = os.path.join(HERE, "audio", "_tmp_" + k); os.makedirs(tmp, exist_ok=True)
        print(f"{k}: {len(paras)} đoạn, {len(chunks)} khối", flush=True)
        async def one(ci, ch):
            pth = os.path.join(tmp, f"{ci:04d}.mp3")
            if not os.path.exists(pth):
                async with sem: await synth(ch[2], pth, a.voice, a.rate, ch[3], a.fake)
            return pth
        files = await asyncio.gather(*[one(i, c) for i, c in enumerate(chunks)])
        marks, t = [], 0.0
        for (u0, u1, _, _), f in zip(chunks, files):
            d = probe(f); marks.append({"u0": u0, "u1": u1, "t0": round(t, 3), "t1": round(t + d, 3)}); t += d
        if shutil.which("ffmpeg") and len(files) > 1:
            lst = os.path.join(tmp, "list.txt"); open(lst, "w").write("".join(f"file '{os.path.abspath(f)}'\n" for f in files))
            subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:a", "libmp3lame", "-b:a", "32k", "-ac", "1", out_mp3])
            marks_scale = probe(out_mp3) / t if t else 1
            for m in marks: m["t0"] = round(m["t0"] * marks_scale, 3); m["t1"] = round(m["t1"] * marks_scale, 3)
            t = probe(out_mp3)
        else:
            with open(out_mp3, "wb") as f:
                for p in files: f.write(open(p, "rb").read())
        json.dump({"units": len(paras), "duration": round(t, 3), "chunks": marks}, open(out_json, "w"))
        shutil.rmtree(tmp, ignore_errors=True)
    print("Xong! Thư mục audio/ đã sẵn sàng. Hãy gửi nó cho Claude để gắn vào trang.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="vi-VN-HoaiMyNeural", help="vi-VN-HoaiMyNeural (nữ) hoặc vi-VN-NamMinhNeural (nam)")
    ap.add_argument("--rate", default="-4%", help="tốc độ, ví dụ -4%% là chậm hơn một chút để dễ nghe giảng")
    ap.add_argument("--only"); ap.add_argument("--parallel", type=int, default=5); ap.add_argument("--fake", action="store_true")
    asyncio.run(run(ap.parse_args()))

if __name__ == "__main__":
    main()
