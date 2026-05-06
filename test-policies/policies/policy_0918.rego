package audit.enforcement.user.validate.policy_0918

# Auto-generated policy 918 (Rego v1 syntax)
# Package: audit.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0918",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0918_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0918_allowed if {
    data.policies.audit.enabled
}
