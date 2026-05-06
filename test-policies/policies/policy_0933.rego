package audit.authentication.context.validate.policy_0933

# Auto-generated policy 933 (Rego v1 syntax)
# Package: audit.authentication.context.validate

# Metadata
metadata := {
    "policy_id": "0933",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0933_allowed = false
policy_0933_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0933_allowed if {
    data.policies.audit.enabled
}
