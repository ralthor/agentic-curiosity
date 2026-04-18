from __future__ import annotations

import base64
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from ai_chat import OpenAIAgent
from ai_chat.models import AnswerPhotoUpload, ChatSession, QuestionPresentation
from ai_chat.storage import get_object_storage

_OCR_SYSTEM_PROMPT = (
    "You are extracting a student's handwritten or typed answer from a photo. "
    "Return only the transcribed answer text. Preserve line breaks, numbering, short equations, and labels when visible. "
    "Do not explain, summarize, or grade the answer. If no answer text is legible, return an empty string."
)


def serialize_answer_photo_upload(upload: AnswerPhotoUpload) -> dict[str, object]:
    return {
        "id": upload.pk,
        "filename": upload.filename,
        "content_type": upload.content_type,
        "byte_size": upload.byte_size,
        "display_order": upload.display_order,
        "extracted_text": upload.extracted_text,
        "content_url": reverse("chat-api-answer-photo-content", args=[upload.pk]),
    }


def upload_answer_photos(
    *,
    session: ChatSession,
    presentation: QuestionPresentation,
    uploaded_files,
) -> list[AnswerPhotoUpload]:
    files = list(uploaded_files)
    if not files:
        raise ValueError("photos must contain at least one image.")

    pending_count = presentation.answer_photo_uploads.filter(attempt__isnull=True).count()
    if pending_count + len(files) > settings.AI_CHAT_ANSWER_PHOTO_MAX_COUNT:
        raise ValueError(
            f"You can attach up to {settings.AI_CHAT_ANSWER_PHOTO_MAX_COUNT} photos to one answer attempt."
        )

    storage = get_object_storage()
    storage.ensure_bucket()
    next_display_order = (
        presentation.answer_photo_uploads.order_by("-display_order", "-id").values_list("display_order", flat=True).first() or 0
    )
    created_uploads: list[AnswerPhotoUpload] = []
    stored_keys: list[str] = []

    try:
        with transaction.atomic():
            for uploaded_file in files:
                content_type = _normalize_content_type(uploaded_file.content_type)
                if content_type not in settings.AI_CHAT_ANSWER_PHOTO_ALLOWED_CONTENT_TYPES:
                    raise ValueError("Only JPEG, PNG, and WEBP images are supported.")
                if uploaded_file.size > settings.AI_CHAT_ANSWER_PHOTO_MAX_BYTES:
                    raise ValueError(
                        f"Each photo must be {settings.AI_CHAT_ANSWER_PHOTO_MAX_BYTES // (1024 * 1024)} MB or smaller."
                    )

                next_display_order += 1
                safe_filename = _normalize_filename(uploaded_file.name)
                storage_key = (
                    f"answer-photos/session-{session.pk}/presentation-{presentation.pk}/"
                    f"{uuid.uuid4().hex}-{safe_filename}"
                )
                uploaded_file.seek(0)
                body = uploaded_file.read()
                storage.put_object(key=storage_key, body=body, content_type=content_type)
                stored_keys.append(storage_key)

                created_uploads.append(
                    AnswerPhotoUpload.objects.create(
                        session=session,
                        presentation=presentation,
                        storage_key=storage_key,
                        filename=safe_filename,
                        content_type=content_type,
                        byte_size=len(body),
                        display_order=next_display_order,
                    )
                )
    except Exception:
        for storage_key in stored_keys:
            _delete_storage_key_quietly(storage_key)
        raise

    return created_uploads


def delete_pending_answer_photo_upload(upload: AnswerPhotoUpload) -> None:
    storage_key = upload.storage_key
    upload.delete()
    _delete_storage_key_quietly(storage_key)


def get_answer_photo_bytes(upload: AnswerPhotoUpload) -> bytes:
    storage = get_object_storage()
    return storage.get_object_bytes(key=upload.storage_key)


def resolve_pending_answer_photo_uploads(
    *,
    session: ChatSession,
    presentation: QuestionPresentation,
    photo_ids: list[int],
) -> list[AnswerPhotoUpload]:
    if not photo_ids:
        return []

    unique_photo_ids: list[int] = []
    for photo_id in photo_ids:
        if photo_id not in unique_photo_ids:
            unique_photo_ids.append(photo_id)

    uploads = list(
        AnswerPhotoUpload.objects.select_for_update()
        .filter(
            id__in=unique_photo_ids,
            session=session,
            presentation=presentation,
            attempt__isnull=True,
        )
        .order_by("display_order", "id")
    )
    if len(uploads) != len(unique_photo_ids):
        raise ValueError("photo_ids must reference pending photos for the current active question.")
    return uploads


def extract_text_for_answer_photo(
    *,
    upload: AnswerPhotoUpload,
    question_text: str,
    question_type_name: str,
) -> str:
    image_bytes = get_answer_photo_bytes(upload)
    base64_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{upload.content_type};base64,{base64_image}"
    agent = OpenAIAgent(model=settings.AI_CHAT_OCR_MODEL)
    extracted_text = agent.ask(
        messages=[
            {"role": "system", "content": _OCR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Question type: {question_type_name}\n"
                            f"Question:\n{question_text}\n\n"
                            "Extract only the student's answer from this image."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                            "detail": "high",
                        },
                    },
                ],
            },
        ]
    ).strip()
    upload.extracted_text = extracted_text
    upload.save(update_fields=["extracted_text", "updated_at"])
    return extracted_text


def build_student_answer_text(*, uploads: list[AnswerPhotoUpload], typed_text: str) -> str:
    sections: list[str] = []
    for index, upload in enumerate(uploads, start=1):
        extracted_text = upload.extracted_text.strip()
        if extracted_text:
            sections.append(f"Photo {index} OCR:\n{extracted_text}")

    cleaned_typed_text = typed_text.strip()
    if cleaned_typed_text:
        sections.append(f"Typed note:\n{cleaned_typed_text}")

    return "\n\n".join(sections).strip()


def cleanup_pending_answer_photo_uploads(*, presentation: QuestionPresentation) -> None:
    uploads = list(presentation.answer_photo_uploads.filter(attempt__isnull=True).order_by("display_order", "id"))
    for upload in uploads:
        delete_pending_answer_photo_upload(upload)


def _normalize_filename(value: str) -> str:
    name = Path(value or "answer-photo").name.strip() or "answer-photo"
    if len(name) <= 255:
        return name
    suffix = Path(name).suffix[:32]
    stem = Path(name).stem[: max(1, 255 - len(suffix))]
    return f"{stem}{suffix}"


def _normalize_content_type(value: str | None) -> str:
    return (value or "").strip().lower()


def _delete_storage_key_quietly(storage_key: str) -> None:
    try:
        storage = get_object_storage()
        storage.delete_object(key=storage_key)
    except Exception:
        return
