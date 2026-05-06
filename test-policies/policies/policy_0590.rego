package access.enforcement.user.deny.utils.policy_0590

# Auto-generated policy 590 (Rego v1 syntax)
# Package: access.enforcement.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0590",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0590_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0590_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
