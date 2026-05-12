import io
import pytest


def test_status_unknown_job_returns_404(client):
    res = client.get("/api/status/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_upload_wrong_extension_returns_400(client):
    data = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
    res = client.post("/api/upload", files=data)
    assert res.status_code == 400


def test_upload_no_file_returns_422(client):
    res = client.post("/api/upload")
    assert res.status_code == 422


def test_delete_unknown_job_returns_404(client):
    res = client.delete("/api/job/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_videos_endpoint_exists(client):
    # Endpoint may require DB; expect 200 (empty list) or 500 if DB unavailable.
    # The important thing is the route exists (not 404/405).
    res = client.get("/api/videos")
    assert res.status_code != 404
    assert res.status_code != 405


def test_takt_timeline_unknown_job(client):
    # Unknown job → 404 (checked before DB query in the handler)
    res = client.get("/api/takt-timeline/nonexistent-job-id-xyz")
    assert res.status_code == 404
