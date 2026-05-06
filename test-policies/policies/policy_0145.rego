package access.enforcement.context.check.logic.policy_0145

# Auto-generated policy 145 (Rego v1 syntax)
# Package: access.enforcement.context.check.logic

# Metadata
metadata := {
    "policy_id": "0145",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0145_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0145_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0145_allowed = false
