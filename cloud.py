import cloudinary  # noqa: F401  (reads CLOUDINARY_URL)
import cloudinary.uploader


def upload(path, public_id, kind):
    """kind: 'video' or 'image'. Returns a public HTTPS URL Instagram can fetch."""
    fn = cloudinary.uploader.upload_large if kind == "video" else cloudinary.uploader.upload
    res = fn(str(path), resource_type=kind, public_id=public_id, folder="ugc",
             overwrite=True, invalidate=True)
    return res["secure_url"]

