from __future__ import annotations

import unittest

from api.services.agent.policy import build_access_context
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionError
from api.services.agent.tools.registry import get_tool_registry


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = get_tool_registry()
        self.exec_context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={},
        )

    def test_list_tools_contains_core_tools(self) -> None:
        tools = self.registry.list_tools()
        ids = {item["tool_id"] for item in tools}
        self.assertIn("marketing.web_research", ids)
        self.assertIn("invoice.create", ids)
        self.assertIn("email.draft", ids)
        self.assertIn("business.route_plan", ids)
        self.assertIn("business.invoice_workflow", ids)
        self.assertIn("business.meeting_scheduler", ids)
        self.assertIn("business.proposal_workflow", ids)
        self.assertIn("web.extract.structured", ids)
        self.assertIn("web.dataset.adapter", ids)
        self.assertIn("data.science.profile", ids)
        self.assertIn("data.science.ml.train", ids)

    def test_execute_draft_tool(self) -> None:
        access = build_access_context(
            user_id="u1",
            settings={"agent.user_role": "member", "agent.access_mode": "restricted"},
        )
        result = self.registry.execute(
            tool_id="email.draft",
            context=self.exec_context,
            access=access,
            prompt="Draft project update email",
            params={"to": "ops@example.com", "subject": "Weekly update"},
        )
        self.assertIn("To: ops@example.com", result.content)
        self.assertGreaterEqual(len(result.events), 1)

    def test_restricted_execute_requires_confirmation(self) -> None:
        access = build_access_context(
            user_id="u1",
            settings={
                "agent.user_role": "admin",
                "agent.access_mode": "restricted",
                "agent.full_access_enabled": False,
            },
        )
        with self.assertRaises(ToolExecutionError):
            self.registry.execute(
                tool_id="email.send",
                context=self.exec_context,
                access=access,
                prompt="send this message",
                params={"to": "ops@example.com", "subject": "x", "body": "y"},
            )

    def test_full_access_member_can_execute_send_tool(self) -> None:
        access = build_access_context(
            user_id="u1",
            settings={
                "agent.user_role": "member",
                "agent.access_mode": "full_access",
                "agent.full_access_enabled": True,
            },
        )
        result = self.registry.execute(
            tool_id="email.send",
            context=self.exec_context,
            access=access,
            prompt="send this message",
            params={"to": "ops@example.com", "subject": "x", "body": "y"},
        )
        self.assertIn("SMTP is not configured", result.summary)


if __name__ == "__main__":
    unittest.main()
