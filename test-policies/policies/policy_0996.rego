package audit.authentication.user.deny.core.policy_0996

# Auto-generated policy 996 (Rego v1 syntax)
# Package: audit.authentication.user.deny.core

# Metadata
metadata := {
    "policy_id": "0996",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0996_allowed if {
    input.user.role == "admin"
}
policy_0996_allowed if {
    data.policies.audit.enabled
}
default policy_0996_allowed = false
policy_0996_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
