package audit.authorization.action.allow.policy_0778

# Auto-generated policy 778 (Rego v1 syntax)
# Package: audit.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0778",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0778_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0778_allowed if {
    data.policies.audit.enabled
}
