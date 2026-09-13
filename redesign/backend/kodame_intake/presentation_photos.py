"""Project-scoped photographs from registered evidence, never sample photos."""
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfReader

from .db import connection
from .settings import ORIGINALS_DIR


def collect_project_photos(document_ids, limit=12):
    ids = list(document_ids)
    if not ids:
        return {}
    with connection() as conn:
        docs = conn.execute("SELECT id,original_name,stored_path FROM intake_documents WHERE id=ANY(%s::uuid[]) ORDER BY uploaded_at", (ids,)).fetchall()
    result, seen = {}, set()
    for doc in docs:
        path = Path(doc["stored_path"]).resolve()
        if not path.is_relative_to(ORIGINALS_DIR.resolve()) or not path.is_file():
            continue
        try:
            if path.suffix.lower() == ".pdf":
                reader = PdfReader(path)
                # Bound work independently of uploaded PDF length.
                candidates = ((im.data, i + 1) for i, p in enumerate(reader.pages[:100]) for im in p.images)
            elif path.suffix.lower() in (".png", ".jpg", ".jpeg"):
                candidates = [(path.read_bytes(), 1)]
            else:
                continue
            for data, page in candidates:
                digest = hashlib.sha256(data).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                image = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
                if image.width < 400 or image.height < 250 or not .6 < image.width / image.height < 2.5:
                    continue
                image.thumbnail((1200, 900))
                output = BytesIO()
                image.save(output, "JPEG", quality=85)
                key = f"photo-{len(result)+1}"
                result[key] = {"data": output.getvalue(), "file_name": doc["original_name"], "page": page,
                               "width": image.width, "height": image.height}
                if len(result) >= limit:
                    return result
        except (OSError, ValueError, KeyError):
            continue
    return result
