"""Réception et validation des photos : type réel (signature), taille, décodage, nombre de pixels, orientation EXIF.

L'image est décodée puis convertie en pixels : les métadonnées (EXIF, dont la position GPS) ne sont jamais conservées.
Rien n'est écrit sur disque, sauf si STORE_UPLOADED_IMAGES=true (copie ré-encodée sans métadonnées)."""
from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import AppError

SIGNATURES = {"jpeg": (b"\xff\xd8\xff",), "png": (b"\x89PNG\r\n\x1a\n",)}
PIL_FORMATS = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}


@dataclass
class LoadedImage:
    bgr: np.ndarray
    width: int
    height: int
    format: str
    sha256: str
    original_size: tuple[int, int]
    orientation_corrected: bool
    downscaled: bool

    def summary(self) -> dict:
        return {"format": self.format, "width": self.width, "height": self.height,
                "original_width": self.original_size[0], "original_height": self.original_size[1],
                "orientation_corrected": self.orientation_corrected, "downscaled": self.downscaled}


def sniff_format(data: bytes) -> str | None:
    """Type réel d'après les premiers octets (le type MIME déclaré par le client n'est pas fiable)."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    for fmt, sigs in SIGNATURES.items():
        if any(data.startswith(s) for s in sigs):
            return fmt
    return None


def load_image(data: bytes, settings: Settings) -> LoadedImage:
    max_bytes = int(settings.max_upload_mb * 1024 * 1024)
    if not data:
        raise AppError("empty_file", "Fichier vide.", 422)
    if len(data) > max_bytes:
        raise AppError("file_too_large", f"Image trop volumineuse (maximum {settings.max_upload_mb:g} Mo).", 413,
                       {"max_bytes": max_bytes, "size": len(data)})
    fmt = sniff_format(data)
    if fmt is None:
        raise AppError("unsupported_media_type", "Format non pris en charge : JPEG, PNG ou WEBP uniquement.", 415)
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                if probe.format != PIL_FORMATS[fmt]:
                    raise AppError("unsupported_media_type", "Le contenu ne correspond pas au format détecté.", 415)
                if probe.width * probe.height > settings.max_image_pixels:
                    raise AppError("image_too_large", "Résolution trop élevée.", 413,
                                   {"max_pixels": settings.max_image_pixels})
                probe.verify()  # structure du fichier (tronqué, corrompu)
            img = Image.open(io.BytesIO(data))
            img.load()
    except AppError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise AppError("image_too_large", "Résolution trop élevée.", 413, {"max_pixels": settings.max_image_pixels})
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise AppError("corrupted_image", "Image illisible ou corrompue.", 422, {"reason": str(exc)[:120]})
    original = img.size
    orientation = img.getexif().get(0x0112, 1)
    img = ImageOps.exif_transpose(img)  # photo de téléphone tournée par l'étiquette EXIF
    if img.mode not in ("RGB", "L"):
        background = Image.new("RGB", img.size, "white")  # transparence -> fond blanc (texte lisible)
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    img = img.convert("RGB")
    downscaled = max(img.size) > settings.max_image_side
    if downscaled:
        img.thumbnail((settings.max_image_side, settings.max_image_side), Image.Resampling.LANCZOS)
    rgb = np.asarray(img)
    return LoadedImage(bgr=np.ascontiguousarray(rgb[:, :, ::-1]), width=img.width, height=img.height, format=fmt,
                       sha256=hashlib.sha256(data).hexdigest(), original_size=original,
                       orientation_corrected=orientation not in (None, 1), downscaled=downscaled)


def store_upload(image: LoadedImage, settings: Settings) -> Path | None:
    """Copie ré-encodée (pixels seulement, sans EXIF) si l'option est activée ; sinon rien n'est écrit."""
    if not settings.store_uploaded_images:
        return None
    folder = Path(settings.data_dir) / "raw" / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{image.sha256}.jpg"
    Image.fromarray(image.bgr[:, :, ::-1]).save(path, "JPEG", quality=90)
    return path
