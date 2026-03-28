"""
Tests for GoogleDocsWriter.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from news_agent.google_docs_writer import GoogleDocsWriter

_FAKE_SA_INFO = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key-id",
    "private_key": (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xHn/ygWep4PAtEsHAMKKEjkfAnkBw6UKpQ==\n"
        "-----END RSA PRIVATE KEY-----\n"
    ),
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def _make_writer(document_id=None):
    """Return a GoogleDocsWriter with a mocked Google Docs service."""
    with patch("news_agent.google_docs_writer.service_account") as mock_sa, \
         patch("news_agent.google_docs_writer.build") as mock_build:
        mock_sa.Credentials.from_service_account_info.return_value = MagicMock()
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        writer = GoogleDocsWriter(
            service_account_info=_FAKE_SA_INFO,
            document_id=document_id,
        )
        writer.service = mock_service
    return writer


class TestCreateDocument:
    def test_creates_new_doc_when_no_id_provided(self):
        writer = _make_writer(document_id=None)
        mock_create_result = {"documentId": "new-doc-123"}
        writer.service.documents.return_value.create.return_value.execute.return_value = (
            mock_create_result
        )
        writer.service.documents.return_value.batchUpdate.return_value.execute.return_value = {}

        doc_id = writer.write(title="Daily News", content="Summary here.")
        assert doc_id == "new-doc-123"
        writer.service.documents.return_value.create.assert_called_once()

    def test_returns_document_id_string(self):
        writer = _make_writer(document_id=None)
        writer.service.documents.return_value.create.return_value.execute.return_value = (
            {"documentId": "abc-123"}
        )
        writer.service.documents.return_value.batchUpdate.return_value.execute.return_value = {}

        result = writer.write("Title", "Body")
        assert result == "abc-123"


class TestAppendToDocument:
    def test_appends_when_document_id_provided(self):
        writer = _make_writer(document_id="existing-doc-456")
        mock_doc = {
            "body": {
                "content": [
                    {"startIndex": 1},
                    {"endIndex": 500},
                ]
            }
        }
        writer.service.documents.return_value.get.return_value.execute.return_value = (
            mock_doc
        )
        writer.service.documents.return_value.batchUpdate.return_value.execute.return_value = {}

        doc_id = writer.write("Today's Digest", "News summary.")
        assert doc_id == "existing-doc-456"
        writer.service.documents.return_value.get.assert_called_once_with(
            documentId="existing-doc-456"
        )

    def test_does_not_call_create_when_appending(self):
        writer = _make_writer(document_id="existing-doc-456")
        mock_doc = {
            "body": {"content": [{"startIndex": 1}, {"endIndex": 100}]}
        }
        writer.service.documents.return_value.get.return_value.execute.return_value = (
            mock_doc
        )
        writer.service.documents.return_value.batchUpdate.return_value.execute.return_value = {}

        writer.write("Title", "Content")
        writer.service.documents.return_value.create.assert_not_called()
