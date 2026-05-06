package access.authorization.policy.allow.policy_0885

# Auto-generated policy 885 (Rego v1 syntax)
# Package: access.authorization.policy.allow

# Metadata
metadata := {
    "policy_id": "0885",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0885_allowed = false
policy_0885_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0885_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
