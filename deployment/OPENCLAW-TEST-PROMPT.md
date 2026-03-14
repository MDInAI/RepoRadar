# OpenClaw Test Prompt

Copy and paste this prompt to OpenClaw to test the Agentic-Workflow integration:

---

Hello! I've just set up Agentic-Workflow dashboard that integrates with you through the Gateway. Can you help me verify the connection is working?

Please check:
1. Can you see the Gateway running on port 18789?
2. Is the Agentic-Workflow backend able to connect to you?
3. Are there any configuration issues I should know about?

The Agentic-Workflow dashboard is running at http://127.0.0.1:3000 and the backend API is at http://127.0.0.1:8000.

---

## What This Tests

This prompt asks OpenClaw to:
- Verify Gateway connectivity
- Check if the integration is properly configured
- Report any issues

## Expected Response

OpenClaw should confirm:
- Gateway is accessible
- Connection is working
- Configuration looks good
