package audit.authentication.user.check.data.policy_0806

# Auto-generated policy 806 (Rego v1 syntax)
# Package: audit.authentication.user.check.data

# Metadata
metadata := {
    "policy_id": "0806",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0806_allowed if {
    input.user.role == "admin"
}
policy_0806_allowed if {
    data.policies.audit.enabled
}
default policy_0806_allowed = false
