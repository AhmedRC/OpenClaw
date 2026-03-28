"""
Google Docs Writer - Creates or appends to a Google Doc with the daily digest.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/documents"]


class GoogleDocsWriter:
    """
    Writes the daily news digest to a Google Document.

    The writer can either create a new document every day or append
    a dated entry to an existing shared document (useful for keeping a
    running log).
    """

    def __init__(
        self,
        service_account_info: dict,
        document_id: Optional[str] = None,
    ):
        """
        Initialize the Google Docs writer.

        Args:
            service_account_info: Dict parsed from a Google service-account
                JSON key file (loaded via json.load).
            document_id: If provided, content is appended to this document.
                         If None, a new document is created on each run.
        """
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=_SCOPES
        )
        self.service = build("docs", "v1", credentials=credentials)
        self.document_id = document_id

    def write(self, title: str, content: str) -> str:
        """
        Write content to a Google Document.

        If a document_id was provided at init time, appends a new dated
        section to that document.  Otherwise creates a brand-new document.

        Args:
            title: Title for the entry / new document.
            content: Body text of the daily digest.

        Returns:
            The document ID of the target document.
        """
        if self.document_id:
            doc_id = self._append_to_document(self.document_id, title, content)
        else:
            doc_id = self._create_document(title, content)
        return doc_id

    def _create_document(self, title: str, content: str) -> str:
        """Create a new Google Document with the given title and content."""
        doc = (
            self.service.documents()
            .create(body={"title": title})
            .execute()
        )
        doc_id = doc["documentId"]
        logger.info("Created new Google Doc: %s", doc_id)

        self._insert_content(doc_id, title, content)
        return doc_id

    def _append_to_document(self, doc_id: str, title: str, content: str) -> str:
        """Append a new dated section to an existing Google Document."""
        self._insert_content(doc_id, title, content, append=True)
        return doc_id

    def _insert_content(
        self, doc_id: str, section_title: str, body: str, append: bool = False
    ) -> None:
        """
        Build a batchUpdate request that inserts formatted text into a doc.

        Args:
            doc_id: Target document ID.
            section_title: Heading text for this entry.
            body: Body text (digest content).
            append: If True, insert at end-of-document; otherwise at index 1.
        """
        if append:
            doc = self.service.documents().get(documentId=doc_id).execute()
            end_index = doc["body"]["content"][-1]["endIndex"] - 1
            insert_index = end_index
        else:
            insert_index = 1

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        full_text = f"{section_title}\n{date_str}\n\n{body}\n\n"

        requests = [
            {
                "insertText": {
                    "location": {"index": insert_index},
                    "text": full_text,
                }
            },
            {
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": insert_index,
                        "endIndex": insert_index + len(section_title) + 1,
                    },
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType",
                }
            },
        ]

        self.service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()
        logger.info("Content written to Google Doc %s.", doc_id)
