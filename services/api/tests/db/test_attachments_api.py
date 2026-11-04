"""OF-1007: adjuntos de movimientos (tickets y facturas)."""

from datetime import timedelta

import pytest

from openfinance.application.attachments import purge_deleted
from openfinance.infrastructure.attachments import FileAttachmentStore
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from openfinance.infrastructure.time import utc_now

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"x" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 32


def tx(client, description: str = "Glovo 50% dto") -> dict:
    return next(
        t for t in client.get("/api/v1/transactions").json() if t["description"] == description
    )


def upload(
    client,
    transaction_id: str,
    content: bytes = PNG,
    name: str = "ticket.png",
    mime: str = "image/png",
):
    return client.post(
        f"/api/v1/transactions/{transaction_id}/attachments",
        files={"file": (name, content, mime)},
    )


class TestUpload:
    @pytest.mark.parametrize(
        ("content", "content_type", "ext"),
        [
            (PNG, "image/png", "png"),
            (PDF, "application/pdf", "pdf"),
            (JPG, "image/jpeg", "jpg"),
            (WEBP, "image/webp", "webp"),
        ],
    )
    def test_accepts_pdf_and_images_by_their_content(
        self, as_raul, seed, content, content_type, ext
    ) -> None:
        r = upload(as_raul, tx(as_raul)["id"], content, "mi ticket.dat", "application/octet-stream")
        assert r.status_code == 201
        a = r.json()["attachment"]
        assert (a["content_type"], a["filename"], a["size"]) == (
            content_type,
            f"mi ticket.{ext}",
            len(content),
        )
        assert tx(as_raul)["attachment_count"] == 1

    @pytest.mark.parametrize(
        ("content", "name", "mime"),
        [
            (
                b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
                "x.svg",
                "image/svg+xml",
            ),
            (b"<html><script>alert(1)</script></html>", "x.html", "text/html"),
            (b"MZ\x90\x00 exe", "virus.png", "image/png"),  # la extensión y el tipo mienten
            (b"", "vacio.png", "image/png"),
            (b"texto plano", "nota.pdf", "application/pdf"),
        ],
    )
    def test_rejects_anything_else_whatever_it_claims(
        self, as_raul, seed, content, name, mime
    ) -> None:
        assert upload(as_raul, tx(as_raul)["id"], content, name, mime).status_code == 422
        assert tx(as_raul)["attachment_count"] == 0

    def test_rejects_big_files(self, as_raul, seed) -> None:
        big = PNG + b"\x00" * (5 * 1024 * 1024)
        assert upload(as_raul, tx(as_raul)["id"], big).status_code in (413, 422)

    def test_at_most_ten_per_movement(self, as_raul, seed) -> None:
        t = tx(as_raul)["id"]
        for _ in range(10):
            assert upload(as_raul, t).status_code == 201
        assert upload(as_raul, t).status_code == 422

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("../../etc/passwd", "passwd.png"),
            ("C:\\Users\\x\\foto.jpg", "foto.png"),
            ("a<b>c.png", "abc.png"),
            ("   ", "adjunto.png"),
            ("..", "adjunto.png"),
        ],
    )
    def test_filenames_are_sanitized(self, as_raul, seed, name, expected) -> None:
        r = upload(as_raul, tx(as_raul)["id"], PNG, name)
        assert r.json()["attachment"]["filename"] == expected

    def test_files_are_stored_by_id_not_by_name(self, as_raul, seed, tmp_path) -> None:
        r = upload(as_raul, tx(as_raul)["id"], PNG, "secreto.png").json()
        files = [p for p in (tmp_path / "attachments").rglob("*") if p.is_file()]
        assert [p.name for p in files] == [r["attachment"]["id"].replace("-", "")]
        assert oct(files[0].stat().st_mode & 0o777) == "0o600"


class TestDownload:
    def test_downloads_as_an_attachment_with_safe_headers(self, as_raul, seed) -> None:
        a = upload(as_raul, tx(as_raul)["id"], PDF, "factura.pdf").json()["attachment"]
        r = as_raul.get(f"/api/v1/attachments/{a['id']}")
        assert r.status_code == 200 and r.content == PDF
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith("attachment;")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "no-store"
        assert "sandbox" in r.headers["content-security-policy"]

    def test_listing(self, as_raul, seed) -> None:
        t = tx(as_raul)["id"]
        upload(as_raul, t, PNG, "a.png")
        upload(as_raul, t, PDF, "b.pdf")
        got = as_raul.get(f"/api/v1/transactions/{t}/attachments").json()
        assert [a["filename"] for a in got] == ["a.png", "b.pdf"]


class TestDeleteAndUndo:
    def test_delete_hides_it_and_undo_brings_it_back(self, as_raul, seed) -> None:
        t = tx(as_raul)["id"]
        a = upload(as_raul, t).json()["attachment"]
        op = as_raul.delete(f"/api/v1/attachments/{a['id']}").json()["operation_id"]
        assert as_raul.get(f"/api/v1/attachments/{a['id']}").status_code == 404
        assert tx(as_raul)["attachment_count"] == 0
        assert as_raul.post(f"/api/v1/changes/{op}/undo").json()["applied"] == 1
        assert as_raul.get(f"/api/v1/attachments/{a['id']}").status_code == 200
        assert as_raul.post(f"/api/v1/changes/{op}/redo").status_code == 200
        assert as_raul.get(f"/api/v1/attachments/{a['id']}").status_code == 404

    def test_undoing_an_upload_removes_it(self, as_raul, seed) -> None:
        t = tx(as_raul)["id"]
        r = upload(as_raul, t).json()
        assert as_raul.post(f"/api/v1/changes/{r['operation_id']}/undo").status_code == 200
        assert as_raul.get(f"/api/v1/transactions/{t}/attachments").json() == []

    def test_old_deleted_ones_are_purged_from_disk_and_database(
        self, as_raul, seed, session_factory, tmp_path
    ) -> None:
        a = upload(as_raul, tx(as_raul)["id"]).json()["attachment"]
        as_raul.delete(f"/api/v1/attachments/{a['id']}")
        store = FileAttachmentStore(tmp_path / "attachments")
        with session_factory() as s:
            assert purge_deleted(SqlUnitOfWork(s), store, utc_now()) == 0  # aún no
            assert purge_deleted(SqlUnitOfWork(s), store, utc_now() + timedelta(days=31)) == 1
        assert [p for p in (tmp_path / "attachments").rglob("*") if p.is_file()] == []


class TestPrivacy:
    def test_partner_cannot_list_download_or_delete_a_personal_attachment(
        self, as_raul, as_elena, seed
    ) -> None:
        pelu = tx(as_elena, "Peluquería")["id"]
        a = upload(as_elena, pelu).json()["attachment"]
        assert as_raul.get(f"/api/v1/transactions/{pelu}/attachments").status_code == 404
        assert as_raul.get(f"/api/v1/attachments/{a['id']}").status_code == 404
        assert as_raul.delete(f"/api/v1/attachments/{a['id']}").status_code == 404
        assert upload(as_raul, pelu).status_code == 404
        assert as_elena.get(f"/api/v1/attachments/{a['id']}").status_code == 200

    def test_other_households_get_404(self, as_ana, as_raul, seed) -> None:
        a = upload(as_raul, tx(as_raul)["id"]).json()["attachment"]
        assert as_ana.get(f"/api/v1/attachments/{a['id']}").status_code == 404

    def test_a_shared_movement_is_open_to_both(self, as_raul, as_elena, seed) -> None:
        a = upload(as_raul, tx(as_raul)["id"]).json()["attachment"]
        assert as_elena.get(f"/api/v1/attachments/{a['id']}").status_code == 200

    def test_requires_a_session(self, client, seed) -> None:
        assert (
            client.get("/api/v1/attachments/00000000-0000-0000-0000-000000000000").status_code
            == 401
        )

    def test_partners_undo_is_404(self, as_raul, as_elena, seed) -> None:
        r = upload(as_raul, tx(as_raul)["id"]).json()
        assert as_elena.post(f"/api/v1/changes/{r['operation_id']}/undo").status_code == 404
