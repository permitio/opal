package audit.enforcement.context.deny.data.policy_0370

# Auto-generated policy 370 (Rego v1 syntax)
# Package: audit.enforcement.context.deny.data

# Metadata
metadata := {
    "policy_id": "0370",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0370_allowed = false
policy_0370_allowed if {
    data.policies.audit.enabled
}
policy_0370_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
