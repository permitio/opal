package security.authentication.user.validate.helpers.policy_0681

# Auto-generated policy 681 (Rego v1 syntax)
# Package: security.authentication.user.validate.helpers

# Metadata
metadata := {
    "policy_id": "0681",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0681_allowed if {
    data.policies.security.enabled
}
policy_0681_allowed if {
    input.user.active
    input.resource.public
}
default policy_0681_allowed = false
policy_0681_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
