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
    
    # Extract the real Message-ID from headers (not Postmark's internal ID)
    message_id = None
    references = None
    
    for header in email.Headers:
        header_name = header.get("Name", "")
        if header_name == "Message-ID" or header_name == "Message-Id":
            message_id = header.get("Value")
        elif header_name == "References":
            references = header.get("Value")
    
    # Fallback to Postmark's MessageID if Message-ID header not found
    if not message_id:
        message_id = email.MessageID if email.MessageID.startswith("<") else f"<{email.MessageID}>"
    
    # Build References header by appending current message_id
    if references:
        references = f"{references} {message_id}"
    else:
        references = message_id
    
    # Ensure subject has Re: prefix
    subject = email.Subject if email.Subject.startswith("Re:") else f"Re: {email.Subject}"
    
    # Reply from the address the email was sent to (for proper threading)
    reply_from = email.To
    
    postmark.emails.send(
        From=reply_from,
        To=email.From,
        Subject=subject,
        TextBody=build_reply_body(email.TextBody),
        Headers={
            "In-Reply-To": message_id,
            "References": references
        },
        TrackOpens=False,
        TrackLinks="None"
    )
    logger.info(f"Sent reply from {reply_from} to {email.From}")
    logger.info(f"Threading headers - In-Reply-To: {message_id}, References: {references}")

    return JSONResponse(
        status_code=200,
        content={"status": "success", "message": "Email received"}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint for fly.io"""
    return {"status": "healthy"}

