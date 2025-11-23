# Postmark Outbound Email Setup Guide

This guide shows you how to send emails (and reply to received emails) using Postmark.

## Step 1: Add Sender Signature in Postmark

1. Go to your Postmark server dashboard
2. Click **"Sender Signatures"** in the left sidebar
3. Click **"Add Domain or Signature"**
4. Choose **"Add Domain"** (recommended) or add individual email addresses
5. Enter your domain: `mail.sorter.social`

## Step 2: Configure DNS Records for Sending

Postmark will provide you with DNS records. Add these to Cloudflare:

### DKIM Record (Required)
This signs your emails cryptographically.

```
Type: TXT
Name: [Postmark provides this, something like: 20241122._domainkey.mail]
Content: [Long DKIM key provided by Postmark]
TTL: Auto
Proxy: DNS only (grey cloud)
```

### Return-Path/CNAME Record (Required)
This handles bounce notifications.

```
Type: CNAME
Name: pm-bounces.mail (or just pm-bounces if root domain)
Target: pm.mtasv.net
TTL: Auto
Proxy: DNS only (grey cloud)
```

### SPF Record (Optional but Recommended)
Add to your existing SPF record or create new one:

```
Type: TXT
Name: mail
Content: v=spf1 include:spf.mtasv.net ~all
TTL: Auto
```

If you already have an SPF record, add `include:spf.mtasv.net` to it.

### DMARC Record (Optional but Recommended)
For email authentication reporting:

```
Type: TXT
Name: _dmarc.mail
Content: v=DMARC1; p=none; rua=mailto:your-email@example.com
TTL: Auto
```

## Step 3: Verify Domain in Postmark

1. After adding DNS records, click **"Verify"** in Postmark
2. Wait for DNS propagation (5-15 minutes)
3. Once verified, you'll see a green checkmark
4. You can now send from any address @mail.sorter.social

## Step 4: Get Your Server API Token

1. In Postmark dashboard, go to **"Servers"**
2. Click on your server
3. Go to **"API Tokens"** tab
4. Copy your **Server API token** (starts with a long string)
5. Add it to fly.io:
   ```bash
   fly secrets set POSTMARK_SERVER_TOKEN="your-server-token-here"
   ```

## Step 5: Update .env.example

Already done! The `.env.example` should include:

```bash
# Postmark
POSTMARK_SERVER_TOKEN=your-server-token-here
POSTMARK_WEBHOOK_SECRET=optional-webhook-secret
```

## Step 6: Send Email with Threading

Here's how to reply to an email while maintaining the thread:

### Basic Reply Example

```python
from postmarker.core import PostmarkClient

# Initialize client
postmark = PostmarkClient(server_token=os.getenv("POSTMARK_SERVER_TOKEN"))

# Send a reply that threads properly
postmark.emails.send(
    From="reply@mail.sorter.social",
    To="original-sender@example.com",
    Subject="Re: Original Subject",  # Keep "Re:" prefix
    TextBody="Your reply text here",
    HtmlBody="<p>Your reply HTML here</p>",
    # Threading headers - CRITICAL for proper threading
    Headers=[
        {
            "Name": "In-Reply-To",
            "Value": original_message_id  # MessageID from inbound webhook
        },
        {
            "Name": "References",
            "Value": original_message_id  # Can include multiple message IDs
        }
    ],
    TrackOpens=False,
    TrackLinks="None"
)
```

### Complete Example in Your Webhook

```python
import os
from postmarker.core import PostmarkClient

# Initialize Postmark client (do this once at app startup)
postmark = PostmarkClient(server_token=os.getenv("POSTMARK_SERVER_TOKEN"))

@app.post("/webhook/postmark")
async def postmark_webhook(email: PostmarkInboundEmail):
    """
    Webhook endpoint for Postmark inbound emails.
    Receives emails sent to anything@mail.sorter.social
    """
    logger.info(f"Received email from {email.From} to {email.To}")
    logger.info(f"Subject: {email.Subject}")
    logger.info(f"Body preview: {email.TextBody[:100]}...")

    # Example: Send an auto-reply
    try:
        # Prepare subject with "Re:" prefix
        reply_subject = email.Subject
        if not reply_subject.startswith("Re:"):
            reply_subject = f"Re: {reply_subject}"

        # Send the reply
        postmark.emails.send(
            From="auto-reply@mail.sorter.social",  # Your sender address
            To=email.From,  # Reply to original sender
            Subject=reply_subject,
            TextBody=f"Thanks for your email! We received:\n\n{email.TextBody}",
            HtmlBody=f"<p>Thanks for your email! We received:</p><blockquote>{email.HtmlBody}</blockquote>",
            # Threading headers - these make it appear as a reply
            Headers=[
                {"Name": "In-Reply-To", "Value": email.MessageID},
                {"Name": "References", "Value": email.MessageID}
            ],
            TrackOpens=False
        )

        logger.info(f"Sent reply to {email.From}")

    except Exception as e:
        logger.error(f"Failed to send reply: {e}")

    return JSONResponse(
        status_code=200,
        content={"status": "success", "message": "Email received"}
    )
```

## Email Threading Headers Explained

To maintain email threads, you need these headers:

1. **In-Reply-To**: The Message-ID of the email you're replying to
2. **References**: Space-separated list of all Message-IDs in the thread
3. **Subject**: Should start with "Re:" for replies

Example for a longer thread:
```python
Headers=[
    {"Name": "In-Reply-To", "Value": "<most-recent-message-id>"},
    {"Name": "References", "Value": "<original-id> <second-id> <most-recent-id>"}
]
```

## Best Practices

1. **Always preserve Message-ID**: Store the MessageID from inbound emails to use in replies
2. **Use proper subject prefixes**: "Re:" for replies, "Fwd:" for forwards
3. **Quote original message**: Include original message in replies (with proper attribution)
4. **From address**: Use a consistent address from your verified domain
5. **Track cautiously**: Consider disabling open/link tracking for privacy

## Testing

### Test Sending Capability

```python
# Simple test script
from postmarker.core import PostmarkClient
import os

postmark = PostmarkClient(server_token=os.getenv("POSTMARK_SERVER_TOKEN"))

response = postmark.emails.send(
    From="test@mail.sorter.social",
    To="your-personal-email@example.com",
    Subject="Test from Postmark",
    TextBody="This is a test email!"
)

print(f"Email sent! Message ID: {response['MessageID']}")
```

### Test Threading

1. Send an email to your app: `test@mail.sorter.social`
2. Your webhook should auto-reply
3. Check your email client - the reply should appear in the same thread

## Verification Tools

- Check DKIM: https://www.mail-tester.com/
- SPF Checker: https://mxtoolbox.com/spf.aspx
- DMARC Checker: https://mxtoolbox.com/dmarc.aspx
- Test email score: https://www.mail-tester.com/

## Common Issues

### Email Going to Spam

1. Verify all DNS records (DKIM, SPF, DMARC)
2. Use a verified sender domain
3. Avoid spam trigger words
4. Include both text and HTML versions
5. Set up DMARC policy gradually (start with p=none)

### Threading Not Working

1. Ensure In-Reply-To header contains exact MessageID
2. Keep "Re:" in subject line
3. References header should include all message IDs in thread
4. Some email clients are picky - test with Gmail, Outlook, etc.

## Rate Limits

Postmark free tier:
- 100 emails/month free
- Then pay-as-you-go: $1.25 per 1,000 emails

For higher volume, consider upgrading your Postmark plan.

## Useful Links

- Postmark Email API Docs: https://postmarkapp.com/developer/api/email-api
- Postmarker Python Docs: https://postmarker.readthedocs.io/
- Email Threading: https://www.jwz.org/doc/threading.html
- DKIM/SPF/DMARC Guide: https://postmarkapp.com/guides/spf-dkim-dmarc
