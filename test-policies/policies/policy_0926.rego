package access.enforcement.policy.check.logic.policy_0926

# Auto-generated policy 926 (Rego v1 syntax)
# Package: access.enforcement.policy.check.logic

# Metadata
metadata := {
    "policy_id": "0926",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0926_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0926_allowed if {
    data.policies.access.enabled
}
policy_0926_allowed if {
    input.user.role == "admin"
}
policy_0926_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
