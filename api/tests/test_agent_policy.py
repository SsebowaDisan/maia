from __future__ import annotations

import unittest

from api.services.agent.policy import (
    ACCESS_MODE_FULL,
    ACCESS_MODE_RESTRICTED,
    ACTION_CLASS_EXECUTE,
    AgentToolCapability,
    build_access_context,
    has_required_role,
    resolve_execution_policy,
)


class AgentPolicyTests(unittest.TestCase):
    def test_access_context_defaults(self) -> None:
        context = build_access_context(user_id="u1", settings={})
        self.assertEqual(context.access_mode, ACCESS_MODE_RESTRICTED)
        self.assertEqual(context.role, "member")
        self.assertFalse(context.full_access_enabled)

    def test_role_gate(self) -> None:
        context = build_access_context(
            user_id="u1",
            settings={"agent.user_role": "analyst"},
        )
        self.assertTrue(has_required_role(context, "analyst"))
        self.assertFalse(has_required_role(context, "admin"))

    def test_full_access_auto_execute_for_execute_actions(self) -> None:
        capability = AgentToolCapability(
            domain="email",
            tool_id="email.send",
            action_class=ACTION_CLASS_EXECUTE,
            minimum_role="admin",
            description="Send email",
            execution_policy="confirm_before_execute",
        )
        context = build_access_context(
            user_id="u1",
            settings={
                "agent.user_role": "admin",
                "agent.access_mode": ACCESS_MODE_FULL,
                "agent.full_access_enabled": True,
            },
        )
        self.assertEqual(resolve_execution_policy(capability, context), "auto_execute")


if __name__ == "__main__":
    unittest.main()
