from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
import logging
import os
from postmarker.core import PostmarkClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="src/templates")

# Initialize Postmark client
postmark_token = os.getenv("POSTMARK_SERVER_TOKEN")
postmark = PostmarkClient(server_token=postmark_token) if postmark_token else None
if not postmark:
    logger.warning("POSTMARK_SERVER_TOKEN not set - email sending disabled")

# Postmark Inbound Email Schema
class PostmarkAttachment(BaseModel):
    Name: str
    Content: str
    ContentType: str
    ContentLength: int

class PostmarkInboundEmail(BaseModel):
    FromName: Optional[str] = None
    From: str
    FromFull: dict
    To: str
    ToFull: List[dict]
    Cc: Optional[str] = None
    CcFull: Optional[List[dict]] = None
    Bcc: Optional[str] = None
    BccFull: Optional[List[dict]] = None
    OriginalRecipient: str
    Subject: str
    MessageID: str
    ReplyTo: Optional[str] = None
    MailboxHash: Optional[str] = None
    Date: str
    TextBody: str
    HtmlBody: str
    StrippedTextReply: Optional[str] = None
    Tag: Optional[str] = None
    Headers: List[dict]
    Attachments: List[PostmarkAttachment] = []

def build_reply_body(original_text: str) -> str:
    """Construct the text body for an auto-reply with quoted text"""
    quoted = "\n".join(f"> {line}" for line in original_text.splitlines())
    return f"Thanks for your email!\n\n{quoted}"

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/webhook/postmark")
async def postmark_webhook(email: PostmarkInboundEmail):
    """
    Webhook endpoint for Postmark inbound emails.
    Receives emails sent to anything@mail.sorter.social
    """
    logger.info(f"Received email from {email.From} to {email.To}")
    logger.info(f"Subject: {email.Subject}")
    logger.info(f"Body preview: {email.TextBody[:100]}...")

    # TODO: Process email and store in database

    # Send auto-reply with proper threading
    if not postmark:
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Email received"}
        )
    
    # Build References header from existing References + MessageID
    references = None
    for header in email.Headers:
        if header.get("Name") == "References":
            references = f"{header.get('Value')} {email.MessageID}"
            break
    if not references:
        references = email.MessageID
    
    # Ensure subject has Re: prefix
    subject = email.Subject if email.Subject.startswith("Re:") else f"Re: {email.Subject}"
    
    postmark.emails.send(
        From="reply@mail.sorter.social",
        To=email.From,
        Subject=subject,
        TextBody=build_reply_body(email.TextBody),
        Headers={
            "In-Reply-To": email.MessageID,
            "References": references
        },
        TrackOpens=False,
        TrackLinks="None"
    )
    logger.info(f"Sent reply to {email.From}")

    return JSONResponse(
        status_code=200,
        content={"status": "success", "message": "Email received"}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint for fly.io"""
    return {"status": "healthy"}

