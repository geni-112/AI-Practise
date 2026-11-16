"""Private diagram OCR. Input and output remain in memory; the worker needs no API keys."""
import csv
import io
import json
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from statistics import median

from PIL import Image, ImageDraw, ImageOps

MAX_BYTES = 2 * 1024 * 1024
SLOTS = threading.BoundedSemaphore(1)
LANGUAGES = "eng+chi_sim"


class RecognitionError(Exception):
    pass


def grayscale(data):
    with Image.open(io.BytesIO(data)) as source:
        width, height = source.size
        if source.format not in ("PNG", "JPEG", "WEBP") or not (
                32 <= width <= 12000 and 32 <= height <= 12000 and width * height <= 25000000):
            raise RecognitionError("INVALID_IMAGE")
        source.draft("L", (1700, 1700))
        # Reduce in strips. Large alpha images should not require two full-size RGBA copies.
        scale = min(1900 / max(width, height), (1700000 / (width * height)) ** 0.5, 2)
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        picture = Image.new("L", size, 255)
        sw, sh = source.size
        for y0 in range(0, size[1], 96):
            y1 = min(y0 + 96, size[1])
            part = source.crop((0, round(y0 * sh / size[1]), sw, round(y1 * sh / size[1])))
            if "A" in part.getbands() or "transparency" in source.info:
                rgba = part.convert("RGBA")
                part = Image.composite(rgba.convert("L"), Image.new("L", rgba.size, 255), rgba.getchannel("A"))
            picture.paste(part.convert("L").resize((size[0], y1-y0), Image.Resampling.BILINEAR), (0, y0))
    sample = sorted(picture.resize((32, 32)).tobytes())
    if median(sample) < 96:
        picture = ImageOps.invert(picture)
    return ImageOps.autocontrast(picture, cutoff=0.3)


def read_labels(image):
    buff = io.BytesIO()
    image.save(buff, format="PPM")
    try:
        proc = subprocess.run(
            [os.environ.get("TESSERACT_BIN", "tesseract"), "stdin", "stdout",
             "-l", LANGUAGES, "--oem", "1", "--psm", "11", "-c", "tessedit_create_tsv=1"],
            input=buff.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=47, check=True, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    except subprocess.TimeoutExpired:
        raise RecognitionError("OCR_TIMEOUT") from None
    except (OSError, subprocess.CalledProcessError):
        raise RecognitionError("OCR_UNAVAILABLE") from None
    groups = {}
    for w in csv.DictReader(io.StringIO(proc.stdout.decode("utf-8", "replace")), delimiter="\t", quoting=csv.QUOTE_NONE):
        if w.get("level") != "5" or not w.get("text"):
            continue
        word = w["text"].strip()[:100]
        if re.fullmatch(r"[一─━—_]+", word) or (word in ("I", "l", "1") and int(w["width"]) > 5 * int(w["height"])):
            continue
        if float(w["conf"]) < 28 or not re.search(r"[\w\u3400-\u9fff]", word):
            continue
        key = (w["block_num"], w["par_num"], w["line_num"])
        groups.setdefault(key, []).append((int(w["left"]), int(w["top"]), int(w["width"]),
                                           int(w["height"]), word, float(w["conf"])))
    labels = []
    for words in groups.values():
        parts = [[]]
        for w in sorted(words):
            if parts[-1]:
                previous = parts[-1][-1]
                if w[0] - previous[0] - previous[2] > max(22, 1.8 * max(previous[3], w[3])):
                    parts.append([])
            parts[-1].append(w)
        for part in parts:
            x, y = min(w[0] for w in part), min(w[1] for w in part)
            right, bottom = max(w[0]+w[2] for w in part), max(w[1]+w[3] for w in part)
            words_text = " ".join(w[4] for w in part)
            words_text = re.sub(r"(?<=[\u3400-\u9fff]) (?=[\u3400-\u9fff])", "", words_text)
            labels.append({"text": words_text[:180], "box": [x, y, right-x, bottom-y],
                           "confidence": round(sum(w[5] for w in part)/len(part))})
    labels.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return labels


def straight_links(image, labels):
    """Associate long uninterrupted strokes with nearby labels. Arrowheads need pixel evidence."""
    mask = image.point(lambda x: 1 if x < 168 else 0)
    draw = ImageDraw.Draw(mask)
    for label in labels:
        x,y,w,h = label["box"]
        draw.rectangle((x-1,y-1,x+w+1,y+h+1),fill=0)
    links = {}
    for vertical in (False, True):
        axis = mask.transpose(Image.Transpose.TRANSPOSE) if vertical else mask
        width, height = axis.size
        data = axis.tobytes()
        pattern = re.compile(b"\x01{%d,}" % max(25, min(75, width//28)))
        boxes = []
        for label in labels:
            x,y,w,h = label["box"]
            boxes.append((label["id"], y,x,h,w) if vertical else (label["id"],x,y,w,h))
        def endpoint(pos, line, before):
            best, distance = None, 1e6
            for lid, x,y,w,h in boxes:
                delta = pos-x-w if before else x-pos
                off = max(0, y-line, line-y-h)
                if -3 <= delta <= max(75, width*.13) and off <= max(13, min(32,h*.9)):
                    score = abs(delta)+4*off+0.12*abs(line-y-h/2)
                    if score < distance:
                        best, distance = lid, score
            return best
        def arrow(pos, line, sign):
            # A wedge has ink on both sides of the shaft, growing toward the interior.
            if not (18 < pos < width-19 and 14 < line < height-15):
                return False
            pairs = []
            for d in range(1, 15):
                col = pos + d*sign
                above = max((k for k in range(1,13) if data[(line-k)*width+col]), default=0)
                below = max((k for k in range(1,13) if data[(line+k)*width+col]), default=0)
                pairs.append(min(above,below))
            return min(pairs[:3]) <= 2 and any(p >= 4 for p in pairs[5:]) and (
                max(pairs[5:]) >= min(pairs[:3])+3 and sum(p>=3 for p in pairs[3:])>=3)
        for y in range(2,height-2):
            for segment in pattern.finditer(data, y*width, (y+1)*width):
                start,end = segment.start()-y*width,segment.end()-y*width-1
                left,right = endpoint(start,y,True),endpoint(end,y,False)
                if not left or not right or left==right:
                    continue
                head_left,head_right = arrow(start,y,1),arrow(end,y,-1)
                direction = "a-to-b" if head_right and not head_left else "b-to-a" if head_left and not head_right else "unknown"
                key = (left,right)
                if key in links and (links[key]["direction"]!="unknown" or direction=="unknown"):
                    continue
                links[key]={"a":left,"b":right,"direction":direction,
                            "axis":"vertical" if vertical else "horizontal"}
                if len(links)>=80:
                    return list(links.values())
    return list(links.values())


def extract(data):
    image = grayscale(data)
    all_labels = read_labels(image)
    labels = all_labels[:100]
    for i,label in enumerate(labels):
        label["id"]="L"+str(i+1)
    connections = straight_links(image, labels) if labels else []
    for label in labels:
        label["box"] = [round(n*1000/image.size[i%2]) for i,n in enumerate(label["box"])]
    return {"engine":"Tesseract 5","languages":LANGUAGES,"coordinateScale":1000,
            "labels":labels,"connections":connections,"truncated":len(all_labels)>len(labels)}


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(55)

    def reply(self, code, result):
        payload=json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.reply(200, {"ready":True}) if self.path=="/health" else self.reply(404,{})

    def do_POST(self):
        if self.path!="/extract":
            return self.reply(404,{})
        try:
            length=int(self.headers.get("Content-Length","0"))
        except ValueError:
            length=0
        if not 0<length<=MAX_BYTES:
            return self.reply(400,{"code":"INVALID_IMAGE"})
        if not SLOTS.acquire(timeout=8):
            return self.reply(503,{"code":"OCR_BUSY"})
        try:
            self.reply(200,extract(self.rfile.read(length)))
        except RecognitionError as error:
            self.reply(422,{"code":str(error)})
        except (OSError,ValueError,Image.DecompressionBombError):
            self.reply(422,{"code":"INVALID_IMAGE"})
        finally:
            SLOTS.release()

    def log_message(self,*args):
        pass


if __name__=="__main__":
    ThreadingHTTPServer((os.environ.get("OCR_BIND","0.0.0.0"),
                         int(os.environ.get("OCR_PORT","8091"))),Handler).serve_forever()
