package audit.authentication.user.validate.policy_0951

# Auto-generated policy 951 (Rego v1 syntax)
# Package: audit.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0951",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0951_allowed if {
    data.policies.audit.enabled
}
policy_0951_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0951_allowed = false
policy_0951_allowed if {
    input.user.active
    input.resource.public
}
