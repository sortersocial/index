"""
Email utilities for sending emails via Postmark
"""
import os
import logging
from typing import Optional, List, Dict
from postmarker.core import PostmarkClient

logger = logging.getLogger(__name__)


class EmailSender:
    """
    Handles sending emails via Postmark with proper threading support
    """

    def __init__(self):
        token = os.getenv("POSTMARK_SERVER_TOKEN")
        if not token:
            logger.warning("POSTMARK_SERVER_TOKEN not set - email sending disabled")
            self.client = None
        else:
            self.client = PostmarkClient(server_token=token)

    def send_reply(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: Optional[str] = None,
        from_address: str = "reply@mail.sorter.social",
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
        track_opens: bool = False,
    ) -> Optional[Dict]:
        """
        Send a reply email with proper threading headers

        Args:
            to: Recipient email address
            subject: Email subject (will add "Re:" if not present)
            text_body: Plain text email body
            html_body: HTML email body (optional)
            from_address: Sender address (must be from verified domain)
            in_reply_to: MessageID of email being replied to
            references: Space-separated MessageIDs for thread history
            track_opens: Whether to track email opens

        Returns:
            Response dict from Postmark or None if sending failed
        """
        if not self.client:
            logger.error("Cannot send email - Postmark client not initialized")
            return None

        # Ensure subject has "Re:" prefix for replies
        if in_reply_to and not subject.startswith("Re:"):
            subject = f"Re: {subject}"

        # Build headers for threading - postmarker expects a dict, not a list
        headers = {}
        if in_reply_to:
            headers["In-Reply-To"] = in_reply_to
            # If no references provided, use in_reply_to as the reference
            headers["References"] = references if references else in_reply_to

        # Build email parameters
        email_params = {
            "From": from_address,
            "To": to,
            "Subject": subject,
            "TextBody": text_body,
            "TrackOpens": track_opens,
            "TrackLinks": "None",
        }

        # Add optional parameters
        if html_body:
            email_params["HtmlBody"] = html_body
        if headers:
            email_params["Headers"] = headers

        response = self.client.emails.send(**email_params)

        logger.info(f"Email sent to {to}, MessageID: {response.get('MessageID')}")
        return response

    def send_email(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: Optional[str] = None,
        from_address: str = "noreply@mail.sorter.social",
        track_opens: bool = False,
    ) -> Optional[Dict]:
        """
        Send a new email (not a reply)

        Args:
            to: Recipient email address
            subject: Email subject
            text_body: Plain text email body
            html_body: HTML email body (optional)
            from_address: Sender address (must be from verified domain)
            track_opens: Whether to track email opens

        Returns:
            Response dict from Postmark or None if sending failed
        """
        if not self.client:
            logger.error("Cannot send email - Postmark client not initialized")
            return None

        # Build email parameters
        email_params = {
            "From": from_address,
            "To": to,
            "Subject": subject,
            "TextBody": text_body,
            "TrackOpens": track_opens,
            "TrackLinks": "None",
        }

        # Add optional parameters
        if html_body:
            email_params["HtmlBody"] = html_body

        response = self.client.emails.send(**email_params)

        logger.info(f"Email sent to {to}, MessageID: {response.get('MessageID')}")
        return response


# Global email sender instance
email_sender = EmailSender()
