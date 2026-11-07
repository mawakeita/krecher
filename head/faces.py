"""Seeing faces: find faces in krēCHer's camera, remember people, recognise them.

Used by head/demo.py (enrol from the operator page, recognition + head tracking run there).
On its own it is a check:
    source ~/venvs/imu/bin/activate
    python ~/krecher/head/faces.py --check     # what OpenCV offers, downloads the models once

Two ways to work, picked automatically:
  * best:     YuNet (finds faces) + SFace (tells people apart): two small model files, downloaded
              once into ~/krecher/models/ (about 40 MB in all).
  * fallback: OpenCV's Haar face finder + LBPH (needs opencv-contrib), no download.
Known faces are saved in ~/krecher/data/faces/ (one file per person). Delete a file to forget someone.
"""
import os
import sys
import time
import urllib.request

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODELS = os.path.join(ROOT, "models")
FACES = os.path.join(ROOT, "data", "faces")

YUNET = ("face_detection_yunet_2023mar.onnx", [
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
])
SFACE = ("face_recognition_sface_2021dec.onnx", [
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
])
SFACE_MATCH = 0.36        # cosine similarity above this = same person (OpenCV's suggested 0.363)
LBPH_MATCH = 75.0         # LBPH distance below this = same person


def fetch(name, urls):
    path = os.path.join(MODELS, name)
    if os.path.exists(path) and os.path.getsize(path) > 100_000:
        return path
    os.makedirs(MODELS, exist_ok=True)
    for url in urls:
        try:
            print("faces: downloading %s ..." % name, flush=True)
            tmp = path + ".part"
            urllib.request.urlretrieve(url, tmp)
            if os.path.getsize(tmp) > 100_000:          # not an error page or a git-lfs pointer
                os.replace(tmp, path)
                return path
            os.remove(tmp)
        except Exception as e:
            print("faces: download failed from %s (%s)" % (url.split('/')[2], e))
    return None


class Faces:
    def __init__(self):
        self.mode = None
        self.people = {}                  # name -> list of feature vectors (sface) / labels (lbph)
        self.det = self.rec = self.cascade = self.lbph = None
        os.makedirs(FACES, exist_ok=True)
        y, s = fetch(*YUNET), fetch(*SFACE)
        try:
            if y and s and hasattr(cv2, "FaceDetectorYN") and hasattr(cv2, "FaceRecognizerSF"):
                self.det = cv2.FaceDetectorYN.create(y, "", (320, 240), 0.8, 0.3, 5)
                self.rec = cv2.FaceRecognizerSF.create(s, "")
                self.mode = "sface"
        except Exception as e:
            print("faces: YuNet/SFace failed (%s)" % e)
        if not self.mode:
            try:
                xml = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                self.cascade = cv2.CascadeClassifier(xml)
                if self.cascade.empty():
                    raise RuntimeError("no cascade file")
                self.lbph = cv2.face.LBPHFaceRecognizer_create()
                self.mode = "lbph"
            except Exception as e:
                print("faces: Haar/LBPH not available either (%s)" % e)
        self._load()

    @property
    def ok(self):
        return self.mode is not None

    # ---- finding faces ---------------------------------------------------
    def find(self, img):
        """Faces in a BGR image, biggest first: list of (x, y, w, h, raw) in that image's pixels."""
        if self.mode == "sface":
            h, w = img.shape[:2]
            self.det.setInputSize((w, h))
            _, found = self.det.detect(img)
            if found is None:
                return []
            out = [(int(f[0]), int(f[1]), int(f[2]), int(f[3]), f) for f in found]
        elif self.mode == "lbph":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            rects = self.cascade.detectMultiScale(gray, 1.15, 5, minSize=(40, 40))
            out = [(int(x), int(y), int(w), int(h), None) for x, y, w, h in rects]
        else:
            return []
        return sorted(out, key=lambda f: -f[2] * f[3])

    def _feature(self, img, face):
        if self.mode == "sface":
            return self.rec.feature(self.rec.alignCrop(img, face[4])).flatten()
        x, y, w, h, _ = face
        gray = cv2.cvtColor(img[max(0, y):y + h, max(0, x):x + w], cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (120, 120))

    # ---- knowing people ----------------------------------------------------
    def _load(self):
        self.people = {}
        for f in sorted(os.listdir(FACES)):
            if f.endswith(".npy"):
                name = f[:-4]
                try:
                    self.people[name] = list(np.load(os.path.join(FACES, f)))
                except Exception as e:
                    print("faces: can't read %s (%s)" % (f, e))
        self._train()

    def _train(self):
        if self.mode != "lbph" or not self.people:
            return
        imgs, labels = [], []
        self._labels = sorted(self.people)
        for i, name in enumerate(self._labels):
            for g in self.people[name]:
                imgs.append(np.asarray(g, dtype=np.uint8)); labels.append(i)
        self.lbph = cv2.face.LBPHFaceRecognizer_create()
        self.lbph.train(imgs, np.array(labels))

    def enroll(self, name, images):
        """Save a person from several BGR images (the biggest face in each). Returns faces used."""
        feats = []
        for img in images:
            found = self.find(img)
            if found:
                feats.append(self._feature(img, found[0]))
        if len(feats) < 3:
            return len(feats)
        name = "".join(c for c in name.lower().strip() if c.isalnum() or c in "-_") or "friend"
        np.save(os.path.join(FACES, name + ".npy"), np.array(feats))
        self._load()
        return len(feats)

    def who(self, img, face):
        """Name of an enrolled person, or None for a stranger."""
        if not self.people:
            return None
        feat = self._feature(img, face)
        if self.mode == "sface":
            best, score = None, 0.0
            for name, feats in self.people.items():
                for f in feats:
                    s = self.rec.match(feat.reshape(1, -1).astype(np.float32),
                                       np.asarray(f, dtype=np.float32).reshape(1, -1),
                                       cv2.FaceRecognizerSF_FR_COSINE)
                    if s > score:
                        best, score = name, s
            return best if score >= SFACE_MATCH else None
        label, dist = self.lbph.predict(feat)
        return self._labels[label] if dist <= LBPH_MATCH else None


def decode(jpeg, width=320):
    """JPEG bytes -> small BGR image for fast face finding."""
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    if w > width:
        img = cv2.resize(img, (width, int(h * width / w)))
    return img


if __name__ == "__main__":
    print("OpenCV", cv2.__version__, "| numpy", np.__version__)
    print("FaceDetectorYN:", hasattr(cv2, "FaceDetectorYN"), "| FaceRecognizerSF:", hasattr(cv2, "FaceRecognizerSF"),
          "| cv2.face:", hasattr(cv2, "face"))
    t0 = time.time()
    f = Faces()
    print("mode:", f.mode or "NONE (face recognition unavailable)", "| known people:", list(f.people) or "none yet",
          "| ready in %.1f s" % (time.time() - t0))
    if "--check" not in sys.argv and len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        img = cv2.imread(sys.argv[1])
        found = f.find(img)
        print("faces in %s: %d" % (sys.argv[1], len(found)), [f.who(img, x) for x in found])
