package access.authentication.context.validate.policy_0710

# Auto-generated policy 710 (Rego v1 syntax)
# Package: access.authentication.context.validate

# Metadata
metadata := {
    "policy_id": "0710",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0710_allowed = false
policy_0710_allowed if {
    data.policies.access.enabled
}
policy_0710_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
