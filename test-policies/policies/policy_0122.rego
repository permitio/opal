package audit.enforcement.policy.validate.policy_0122

# Auto-generated policy 122 (Rego v1 syntax)
# Package: audit.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0122",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0122_allowed = false
policy_0122_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0122_allowed if {
    data.policies.audit.enabled
}
