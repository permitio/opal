package access.authorization.policy.check.utils.policy_0207

# Auto-generated policy 207 (Rego v1 syntax)
# Package: access.authorization.policy.check.utils

# Metadata
metadata := {
    "policy_id": "0207",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0207_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0207_allowed if {
    input.user.role == "admin"
}
default policy_0207_allowed = false
policy_0207_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
