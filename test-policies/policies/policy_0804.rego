package audit.enforcement.policy.allow.data.policy_0804

# Auto-generated policy 804 (Rego v1 syntax)
# Package: audit.enforcement.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0804",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0804_allowed = false
policy_0804_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0804_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
