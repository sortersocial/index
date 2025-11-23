from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="src/templates")

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

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/webhook/postmark")
async def postmark_webhook(email: PostmarkInboundEmail):
    """
    Webhook endpoint for Postmark inbound emails.
    Receives emails sent to anything@sorter.social
    """
    logger.info(f"Received email from {email.From} to {email.To}")
    logger.info(f"Subject: {email.Subject}")
    logger.info(f"Body preview: {email.TextBody[:100]}...")

    # TODO: Process email and store in database
    # For now, just log and return success

    return JSONResponse(
        status_code=200,
        content={"status": "success", "message": "Email received"}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint for fly.io"""
    return {"status": "healthy"}

