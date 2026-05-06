package access.validation.user.verify.policy_0146

# Auto-generated policy 146 (Rego v1 syntax)
# Package: access.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0146",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0146_allowed if {
    input.user.active
    input.resource.public
}
default policy_0146_allowed = false
policy_0146_allowed if {
    data.policies.access.enabled
}
policy_0146_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
